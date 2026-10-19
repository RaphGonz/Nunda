"""Étape 1 de l'ingestion : extraction du texte (SPEC.md §5).

pypdfium2 (Apache 2.0 / BSD) lit chaque caractère et sa boîte ; une page qui a moins de
`ocr_caracteres_min` caractères natifs passe à Tesseract (`fra`), qui donne une confiance
par mot. Les mots des deux sources suivent le même chemin : découpe en blocs (haut vers
bas ; colonnes détectées par les gouttières entre groupes d'abscisses), lignes, puis
paragraphes (écart entre deux lignes plus grand qu'une part de la hauteur médiane des
lignes ; boîtes de police pour le texte natif, boîtes serrées pour l'OCR, d'où deux
facteurs). Le code recolle les lignes et les mots coupés en fin de ligne ; il ne change
rien d'autre. Coordonnées en points, origine en haut à gauche.
"""

import csv
import io
import shutil
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from ccm.config import ExtractionConfig

RACINE = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Mot:
    texte: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0


@dataclass(frozen=True)
class Paragraphe:
    texte: str
    page: int  # page du fichier où il commence (1, 2, …)
    ligne: int  # rang de sa première ligne dans la page (0, 1, …)
    mots: tuple[tuple[int, int, float], ...]  # (début, fin, confiance) de chaque mot

    def conf(self, debut: int, fin: int) -> float:
        """Moyenne des confiances des mots de texte[debut:fin]."""
        c = [x for d, f, x in self.mots if d < fin and f > debut]
        return sum(c) / len(c) if c else 1.0


@dataclass(frozen=True)
class Page:
    numero: int
    ocr: bool
    lignes: list[list[Mot]]  # ordre de lecture
    paragraphes: list[list[list[Mot]]]  # lignes de chaque paragraphe


def _mots_natifs(page: pdfium.PdfPage) -> list[Mot]:
    tp = page.get_textpage()
    hauteur = page.get_height()
    mots, courant = [], []

    def fermer():
        if courant:
            texte = "".join(c for c, _ in courant)
            boites = [b for _, b in courant]
            mots.append(
                Mot(
                    texte,
                    min(b[0] for b in boites),
                    hauteur - max(b[3] for b in boites),
                    max(b[2] for b in boites),
                    hauteur - min(b[1] for b in boites),
                )
            )
            courant.clear()

    for i in range(tp.count_chars()):
        c = tp.get_text_range(i, 1)
        if c.isspace() or not c:
            fermer()
        elif c == "￾":  # pdfium : trait d'union de fin de ligne, sans saut de ligne
            courant.append(("-", tp.get_charbox(i, loose=True)))
            fermer()
        else:
            courant.append((c, tp.get_charbox(i, loose=True)))
    fermer()
    return mots


def tesseract(cfg: ExtractionConfig) -> str | None:
    """Chemin de l'exécutable Tesseract, ou None s'il est absent."""
    for c in cfg.tesseract:
        if trouve := shutil.which(c):
            return trouve
    return None


def _mots_ocr(page: pdfium.PdfPage, cfg: ExtractionConfig) -> list[Mot]:
    exe = tesseract(cfg)
    if exe is None:
        raise RuntimeError("Tesseract introuvable (configs/ingest.yaml : extraction.tesseract)")
    image = page.render(scale=cfg.ocr_dpi / 72, grayscale=True)
    octets, pas = bytes(image.buffer), image.stride
    larg, haut = image.width, image.height
    pgm = f"P5 {larg} {haut} 255\n".encode() + b"".join(
        octets[k * pas : k * pas + larg] for k in range(haut)
    )
    commande = [exe, "stdin", "stdout", "-l", cfg.ocr_langue, "--dpi", str(cfg.ocr_dpi)]
    tessdata = RACINE / cfg.tessdata
    if tessdata.is_dir():
        commande += ["--tessdata-dir", str(tessdata)]
    sortie = subprocess.run(
        commande + ["-c", "tessedit_create_tsv=1"], input=pgm, capture_output=True, check=True
    )
    k = 72 / cfg.ocr_dpi
    mots = []
    tsv = io.StringIO(sortie.stdout.decode("utf-8"))
    for r in csv.DictReader(tsv, delimiter="\t", quoting=csv.QUOTE_NONE):
        texte = (r["text"] or "").strip()
        if r["level"] == "5" and texte and float(r["conf"]) >= 0:
            x, y, w, hh = (int(r[c]) for c in ("left", "top", "width", "height"))
            mots.append(Mot(texte, x * k, y * k, (x + w) * k, (y + hh) * k, float(r["conf"]) / 100))
    return mots


def _gouttiere(mots: list[Mot], cfg: ExtractionConfig) -> float | None:
    """Abscisse d'une coupe entre deux colonnes, assez larges toutes les deux."""
    gauche, droite = min(m.x0 for m in mots), max(m.x1 for m in mots)
    fin = None
    for m in sorted(mots, key=lambda m: m.x0):
        if fin is not None and m.x0 - fin >= cfg.gouttiere_min:
            if min(fin - gauche, droite - m.x0) >= cfg.largeur_min_colonne:
                return (fin + m.x0) / 2
        fin = m.x1 if fin is None else max(fin, m.x1)
    return None


def _bandes(mots: list[Mot], ecart: float) -> list[list[Mot]]:
    bandes, fin = [], None
    for m in sorted(mots, key=lambda m: m.y0):
        if fin is None or m.y0 - fin >= ecart:
            bandes.append([])
        bandes[-1].append(m)
        fin = m.y1 if fin is None else max(fin, m.y1)
    return bandes


def _blocs(mots: list[Mot], cfg: ExtractionConfig, ecart: float) -> list[list[Mot]]:
    """Coupe XY : colonnes de gauche à droite, sinon bandes de haut en bas."""
    if (x := _gouttiere(mots, cfg)) is not None:
        return _blocs([m for m in mots if m.x1 <= x], cfg, ecart) + _blocs(
            [m for m in mots if m.x1 > x], cfg, ecart
        )
    bandes = _bandes(mots, ecart)
    if len(bandes) > 1:
        return [b for bande in bandes for b in _blocs(bande, cfg, ecart)]
    return [mots]


def _haut_bas(ligne: list[Mot]) -> tuple[float, float]:
    return min(m.y0 for m in ligne), max(m.y1 for m in ligne)


def _lignes(mots: list[Mot]) -> list[list[Mot]]:
    lignes: list[list[Mot]] = []
    for m in sorted(mots, key=lambda m: (m.y0 + m.y1) / 2):
        c = (m.y0 + m.y1) / 2
        if lignes:
            haut, bas = _haut_bas(lignes[-1])
            if abs(c - (haut + bas) / 2) < (bas - haut) / 2:
                lignes[-1].append(m)
                continue
        lignes.append([m])
    return [sorted(d, key=lambda m: m.x0) for d in lignes]


def lire_page(page: pdfium.PdfPage, numero: int, cfg: ExtractionConfig) -> Page:
    mots = _mots_natifs(page)
    ocr = sum(len(m.texte) for m in mots) < cfg.ocr_caracteres_min
    if ocr:
        mots = _mots_ocr(page, cfg)
    if not mots:
        return Page(numero, ocr, [], [])
    hauteur = statistics.median(m.y1 - m.y0 for m in mots)
    blocs = [_lignes(b) for b in _blocs(mots, cfg, cfg.ecart_bloc * hauteur)]
    facteur = cfg.facteur_paragraphe_ocr if ocr else cfg.facteur_paragraphe
    seuil = facteur * statistics.median(_haut_bas(d)[1] - _haut_bas(d)[0] for b in blocs for d in b)
    paragraphes = []
    for b in blocs:
        for k, ligne in enumerate(b):
            if k == 0 or _haut_bas(ligne)[0] - _haut_bas(b[k - 1])[1] > seuil:
                paragraphes.append([])
            paragraphes[-1].append(ligne)
    return Page(numero, ocr, [d for b in blocs for d in b], paragraphes)


def lire_pdf(chemin: Path, cfg: ExtractionConfig) -> list[Page]:
    doc = pdfium.PdfDocument(chemin)
    try:
        return [lire_page(doc[k], k + 1, cfg) for k in range(len(doc))]
    finally:
        doc.close()


def texte_ligne(ligne: list[Mot]) -> str:
    return " ".join(m.texte for m in ligne)


def _recoller(lignes: list[list[Mot]]) -> tuple[str, list[tuple[int, int, float]]]:
    """Mots joints par une espace. Après un trait d'union en fin de ligne, la ligne suivante
    est recollée sans espace : le trait tombe devant une minuscule (mot coupé), il reste
    devant une majuscule (mot composé, « Import-Export »). Rend aussi la position et la
    confiance de chaque mot dans le texte."""
    texte, spans = "", []
    for ligne in lignes:
        for k, m in enumerate(ligne):
            if k == 0 and len(texte) > 1 and texte[-1] == "-" and texte[-2].isalpha():
                if m.texte[:1].islower():
                    texte = texte[:-1]
                d, _, c = spans.pop()
                spans.append((d, len(texte) + len(m.texte), min(c, m.conf)))
            else:
                texte += " " if texte else ""
                spans.append((len(texte), len(texte) + len(m.texte), m.conf))
            texte += m.texte
    return texte, spans


def _coupe_par_la_page(fin: list[Mot], debut: list[Mot], droite: float) -> bool:
    """Une ligne de bas de page continue sur la page suivante si le premier mot de la
    suivante ne tenait pas dans la place restante : la ligne a été coupée là."""
    espace = (
        statistics.median(b.x0 - a.x1 for a, b in zip(fin, fin[1:], strict=False))
        if len(fin) > 1
        else 0
    )
    return fin[-1].x1 + espace + (debut[0].x1 - debut[0].x0) > droite


def paragraphes(pages: list[Page]) -> list[Paragraphe]:
    """Paragraphes d'une suite de pages (une pièce), recollés d'une page à l'autre."""
    droite = max((m.x1 for p in pages for d in p.lignes for m in d), default=0)
    groupes: list[tuple[int, int, list[list[Mot]]]] = []
    for p in pages:
        rang = 0
        for k, par in enumerate(p.paragraphes):
            if k == 0 and groupes and _coupe_par_la_page(groupes[-1][2][-1], par[0], droite):
                groupes[-1][2].extend(par)
            else:
                groupes.append((p.numero, rang, list(par)))
            rang += len(par)
    out = []
    for numero, rang, lignes in groupes:
        texte, mots = _recoller(lignes)
        out.append(Paragraphe(texte, numero, rang, tuple(mots)))
    return out
