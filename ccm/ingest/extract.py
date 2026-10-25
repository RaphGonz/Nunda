"""Étape 1 de l'ingestion : extraction du texte (SPEC.md §5).

pypdfium2 (Apache 2.0 / BSD) lit chaque caractère et sa boîte ; une page qui a moins de
`ocr_caracteres_min` caractères natifs passe à Tesseract (`fra`), qui donne une confiance
par mot. Les mots des deux sources suivent le même chemin : découpe en blocs (haut vers
bas ; colonnes détectées par les gouttières entre groupes d'abscisses), lignes, puis
paragraphes (écart entre deux lignes plus grand qu'une part de la hauteur médiane des
lignes ; boîtes de police pour le texte natif, boîtes serrées pour l'OCR, d'où deux
facteurs). Le code recolle les lignes et les mots coupés en fin de ligne ; il ne change
rien d'autre. Coordonnées en points, origine en haut à gauche.

Tableaux (étape 4) : les cellules sont les rectangles tracés de la page (objets chemin de
pdfium). Les rectangles de même ordonnée et de même hauteur forment une rangée ; une
rangée d'au moins `cellules_min` cellules est une ligne de tableau. Les mots des cellules
sortent du texte courant ; la rangée y entre comme un seul mot (sa boîte), placé par la
coupe XY comme le reste, puis devient un paragraphe à part. Un tableau en image (OCR)
n'est pas détecté.
"""

import csv
import io
import shutil
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from ccm.config import ExtractionConfig, TableauxConfig

RACINE = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Mot:
    texte: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0
    cellules: tuple[tuple["Mot", ...], ...] | None = None  # rangée : mots de chaque cellule


@dataclass(frozen=True)
class Paragraphe:
    texte: str
    page: int  # page du fichier où il commence (1, 2, …)
    ligne: int  # rang de sa première ligne dans la page (0, 1, …)
    mots: tuple[tuple[int, int, float], ...]  # (début, fin, confiance) de chaque mot
    rangee: bool = False  # ligne de tableau : « cellule | cellule | … »

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


def _rangees(page: pdfium.PdfPage, cfg: TableauxConfig) -> list[list[tuple[float, ...]]]:
    """Rangées de cellules tracées (x0, y0, x1, y1), chacune de gauche à droite."""
    hauteur = page.get_height()
    boites = []
    for o in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH]):
        g, b, d, h = o.get_bounds()
        if d - g >= cfg.cote_min and h - b >= cfg.cote_min:
            boites.append((g, hauteur - h, d, hauteur - b))
    rangees: list[list[tuple[float, ...]]] = []
    for c in sorted(boites, key=lambda c: (c[1], c[0])):
        r = rangees[-1] if rangees else None
        if r and abs(r[0][1] - c[1]) <= cfg.tolerance and abs(r[0][3] - c[3]) <= cfg.tolerance:
            r.append(c)
        else:
            rangees.append([c])
    return [r for r in rangees if len(r) >= cfg.cellules_min]


def _sortir_tableaux(mots: list[Mot], rangees: list[list[tuple[float, ...]]]) -> list[Mot]:
    """Remplace les mots des cellules par un mot par rangée (sa boîte, ses cellules)."""

    def dans(m: Mot, c: tuple[float, ...]) -> bool:
        x, y = (m.x0 + m.x1) / 2, (m.y0 + m.y1) / 2
        return c[0] <= x <= c[2] and c[1] <= y <= c[3]

    pris: set[int] = set()
    out = []
    for r in rangees:
        cellules = []
        for c in r:
            ks = [k for k, m in enumerate(mots) if k not in pris and dans(m, c)]
            pris.update(ks)
            cellules.append(tuple(mots[k] for k in ks))
        if any(cellules):
            texte = " | ".join(texte_ligne(list(c)) for c in cellules)
            out.append(Mot(texte, r[0][0], r[0][1], r[-1][2], r[0][3], cellules=tuple(cellules)))
    return [m for k, m in enumerate(mots) if k not in pris] + out


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
    else:
        mots = _sortir_tableaux(mots, _rangees(page, cfg.tableaux))
    if not mots:
        return Page(numero, ocr, [], [])
    texte = [m for m in mots if m.cellules is None] or mots
    hauteur = statistics.median(m.y1 - m.y0 for m in texte)
    blocs = [_lignes(b) for b in _blocs(mots, cfg, cfg.ecart_bloc * hauteur)]
    facteur = cfg.facteur_paragraphe_ocr if ocr else cfg.facteur_paragraphe
    hauteurs = [_haut_bas(d)[1] - _haut_bas(d)[0] for b in blocs for d in b if not _est_rangee(d)]
    seuil = facteur * statistics.median(hauteurs or [hauteur])
    paragraphes = []
    for b in blocs:
        for k, ligne in enumerate(b):
            if (
                k == 0
                or _est_rangee(ligne)
                or _est_rangee(b[k - 1])
                or _haut_bas(ligne)[0] - _haut_bas(b[k - 1])[1] > seuil
            ):
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


def _est_rangee(ligne: list[Mot]) -> bool:
    return ligne[0].cellules is not None


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
            fin = groupes[-1][2][-1] if groupes else None
            if (
                k == 0
                and fin is not None
                and not _est_rangee(fin)
                and not _est_rangee(par[0])
                and _coupe_par_la_page(fin, par[0], droite)
            ):
                groupes[-1][2].extend(par)
            else:
                groupes.append((p.numero, rang, list(par)))
            rang += len(par)
    out = []
    for numero, rang, lignes in groupes:
        if _est_rangee(lignes[0]):
            out.append(_rangee(lignes[0][0], numero, rang))
        else:
            texte, mots = _recoller(lignes)
            out.append(Paragraphe(texte, numero, rang, tuple(mots)))
    return out


def _rangee(rangee: Mot, numero: int, rang: int) -> Paragraphe:
    """Chaque cellule recollée comme un paragraphe ; cellules jointes par « | »."""
    texte, spans = "", []
    for k, cellule in enumerate(rangee.cellules or ()):
        t, s = _recoller(_lignes(list(cellule))) if cellule else ("", [])
        texte += " | " if k else ""
        spans += [(d + len(texte), f + len(texte), c) for d, f, c in s]
        texte += t
    return Paragraphe(texte, numero, rang, tuple(spans), rangee=True)
