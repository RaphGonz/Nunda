"""Articles en vigueur des codes, lus dans le dump LEGI de la DILA (SPEC.md §12).

L'archive (plusieurs millions de petits fichiers) est lue en flux : rien n'est décompressé sur
le disque. Gardés : les articles sous `code_en_vigueur`, à l'état VIGUEUR, dont la période
contient la date du dump. Ce dossier contient aussi les anciennes versions de chaque article.
"""

import hashlib
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from ccm.data.droit import Texte, net
from ccm.schema import TypePiece

_BLOCS = {"p", "div", "br", "table", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
          "blockquote", "center", "hr"}  # fmt: skip


def paragraphes(contenu: ET.Element) -> tuple[tuple[str, bool], ...]:
    """Paragraphes du HTML d'un article ; une rangée de tableau donne « cellule | cellule »."""
    out: list[tuple[str, bool]] = []
    cour: list[str] = []

    def fermer() -> None:
        t = net("".join(cour))
        cour.clear()
        if t:
            out.append((t, False))

    def visiter(el: ET.Element) -> None:
        nom = el.tag.lower()
        if nom == "tr":
            fermer()
            cellules = [net("".join(c.itertext())) for c in el]
            if any(cellules):  # une rangée vide n'est pas une proposition
                out.append((" | ".join(cellules), True))
            return
        if nom in _BLOCS:
            fermer()
        cour.append(el.text or "")
        for f in el:
            visiter(f)
            cour.append(f.tail or "")
        if nom in _BLOCS:
            fermer()

    visiter(contenu)
    fermer()
    return tuple(out)


def _article(octets: bytes, chemin: str, date_dump: str, bilan: Counter) -> Texte | None:
    racine = ET.fromstring(octets)
    meta = racine.find("META/META_SPEC/META_ARTICLE")
    if meta is None or meta.findtext("ETAT") != "VIGUEUR":
        bilan["pas_en_vigueur"] += 1
        return None
    if not (meta.findtext("DATE_DEBUT", "") <= date_dump < meta.findtext("DATE_FIN", "9999")):
        bilan["hors_periode"] += 1
        return None
    contenu = racine.find("BLOC_TEXTUEL/CONTENU")
    pars = paragraphes(contenu) if contenu is not None else ()
    if not pars:
        bilan["sans_texte"] += 1
        return None
    titre = racine.find("CONTEXTE/TEXTE/TITRE_TXT")
    code = net(titre.get("c_titre_court") or titre.text or "") if titre is not None else ""
    tete = net(f"{code}, article {meta.findtext('NUM') or ''}")
    identifiant = racine.findtext("META/META_COMMUN/ID", "")
    bilan["en_vigueur"] += 1
    return Texte(identifiant, chemin, hashlib.sha256(octets).hexdigest(), TypePiece.LOI, tete, pars)


def textes(archive: Path, date_dump: str, bilan: Counter | None = None) -> Iterator[Texte]:
    """Les articles en vigueur, en flux. `bilan` compte ce qui est lu, gardé, écarté."""
    bilan = Counter() if bilan is None else bilan
    with tarfile.open(archive, "r|gz") as t:
        for m in t:
            bilan["membres"] += 1
            if not (m.isfile() and "/code_en_vigueur/" in m.name and "/article/" in m.name):
                continue
            f = t.extractfile(m)
            if f is None:
                continue
            texte = _article(f.read(), m.name, date_dump, bilan)
            if texte is not None:
                yield texte
