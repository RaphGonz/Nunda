"""Rendu d'une pièce en PDF natif (SPEC.md §5 : lu par PyMuPDF à l'ingestion).

Police Helvetica intégrée (sous-ensemble), coupure des lignes aux espaces seulement,
tableau tracé avec ses filets pour les lignes de relevé. Aucune date ni identifiant
aléatoire dans le fichier : même pièce, mêmes octets.
"""

from functools import cache

import pymupdf

from ccm.config import PdfConfig
from ccm.data.worldgen.pieces import Piece


@cache
def _police(nom: str) -> pymupdf.Font:
    return pymupdf.Font(nom)


@cache
def _avance(nom: str, c: str) -> float:
    return _police(nom).glyph_advance(ord(c))


def _couper(texte: str, police: str, taille: float, largeur: float) -> list[str]:
    lignes, courante = [], ""
    for mot in texte.split(" "):
        essai = f"{courante} {mot}" if courante else mot
        if courante and sum(_avance(police, c) for c in essai) * taille > largeur:
            lignes.append(courante)
            courante = mot
        else:
            courante = essai
    return lignes + [courante]


class _Page:
    def __init__(self, doc: pymupdf.Document, cfg: PdfConfig):
        self.doc, self.cfg = doc, cfg
        self.page = self.ecrivain = None
        self.nouvelle()

    def nouvelle(self):
        self.fermer()
        self.page = self.doc.new_page(width=self.cfg.largeur, height=self.cfg.hauteur)
        self.ecrivain = pymupdf.TextWriter(self.page.rect)
        self.y = self.cfg.marge

    def place(self, hauteur: float):
        if self.y + hauteur > self.cfg.hauteur - self.cfg.marge:
            self.nouvelle()

    def fermer(self):
        if self.ecrivain is not None:
            self.ecrivain.write_text(self.page)


def rendre_pdf(piece: Piece, cfg: PdfConfig) -> bytes:
    normale, grasse = "helv", "hebo"
    t, lh = cfg.taille, cfg.interligne
    largeur = cfg.largeur - 2 * cfg.marge
    doc = pymupdf.open()
    doc.set_metadata({})
    p = _Page(doc, cfg)
    for ligne in piece.lignes:
        if ligne.genre == "LIGNE_TABLEAU":
            cellules = ligne.texte.split(" | ")
            police = grasse if "/colonnes/" in ligne.gabarit else normale
            m = cfg.marge_cellule
            largeurs = [largeur * c for c in cfg.colonnes]
            coupees = [
                _couper(c, police, t, w - 2 * m) for c, w in zip(cellules, largeurs, strict=True)
            ]
            hauteur = max(len(c) for c in coupees) * lh + 2 * m
            p.place(hauteur)
            x = cfg.marge
            for lignes, w in zip(coupees, largeurs, strict=True):
                p.page.draw_rect(pymupdf.Rect(x, p.y, x + w, p.y + hauteur), width=0.5)
                for k, s in enumerate(lignes):
                    p.ecrivain.append((x + m, p.y + m + (k + 1) * lh - 3), s, _police(police), t)
                x += w
            p.y += hauteur
            continue
        police = grasse if ligne.genre == "EN_TETE" else normale
        for s in _couper(ligne.texte, police, t, largeur):
            p.place(lh)
            p.ecrivain.append((cfg.marge, p.y + lh - 3), s, _police(police), t)
            p.y += lh
        p.y += cfg.espace_paragraphe
    p.fermer()
    doc.subset_fonts()
    return doc.tobytes(garbage=4, deflate=True, no_new_id=True)
