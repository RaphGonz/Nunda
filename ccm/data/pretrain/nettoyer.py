"""Nettoyage d'un document brut (SPEC.md §12) : normalisation, restes de wiki, filtres.

Normalisation NFC, caractères de contrôle et blancs ; retrait des marques réservées à
l'entrée du modèle (⟦k⟧, [P], [/P]) ; lignes de tables et de gabarits restées dans le texte
d'un article ; en-tête et licence du Projet Gutenberg. Filtres : longueur, part de lettres,
qualité de l'OCR (livres). Le dédoublonnage exact (SHA-1 du texte nettoyé) se fait dans la
chaîne, sur tout le corpus.
"""

import hashlib
import re
import unicodedata

from ccm.config import NettoyageConfig, SourcePretrain

_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏﻿]")
_RESERVE = re.compile(r"⟦|⟧|\[/?P\]")
_BLANCS = re.compile(r"[ \t  -  　]+")
_LIGNE_WIKI = re.compile(r"^\s*(?:\{\||\|\}|\|-|!|\||\{\{|\}\}|__\w+__)")
_GUTENBERG_DEBUT = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*\n")
_GUTENBERG_FIN = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG")
_MOT = re.compile(r"\S+")


def normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFC", texte.replace("\r\n", "\n").replace("\r", "\n"))
    texte = _RESERVE.sub(" ", _CONTROLE.sub("", texte))
    lignes = [_BLANCS.sub(" ", ligne).strip() for ligne in texte.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lignes)).strip()


def sans_gutenberg(texte: str) -> str:
    if m := _GUTENBERG_DEBUT.search(texte):
        texte = texte[m.end() :]
    if m := _GUTENBERG_FIN.search(texte):
        texte = texte[: m.start()]
    return texte


def sans_restes_wiki(texte: str) -> str:
    return "\n".join(ligne for ligne in texte.split("\n") if not _LIGNE_WIKI.match(ligne))


def rejet(texte: str, s: SourcePretrain, cfg: NettoyageConfig) -> str | None:
    """Raison du rejet du texte nettoyé, ou None s'il est gardé."""
    if len(texte) < cfg.longueur_min:
        return "trop court"
    pleins = sum(1 for c in texte if not c.isspace())
    if sum(1 for c in texte if c.isalpha()) < cfg.part_lettres_min * pleins:
        return "peu de lettres"
    if s.ocr:
        mots = _MOT.findall(texte)
        nus = (m.strip(".,;:!?«»\"'()") for m in mots)
        bons = sum(1 for m in nus if len(m) > 1 and m.replace("-", "").replace("'", "").isalpha())
        if bons < cfg.part_mots_ocr_min * len(mots):
            return "OCR"
    return None


def nettoyer(texte: str, s: SourcePretrain, cfg: NettoyageConfig) -> tuple[str, str | None]:
    """(texte nettoyé, raison du rejet ou None)."""
    if s.gutenberg:
        texte = sans_gutenberg(texte)
    if s.lecteur == "wiki":
        texte = sans_restes_wiki(texte)
    texte = normaliser(texte)
    return texte, rejet(texte, s, cfg)


def empreinte(texte: str) -> str:
    return hashlib.sha1(texte.encode("utf-8")).hexdigest()
