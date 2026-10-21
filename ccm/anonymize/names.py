"""Norme d'un nom (SPEC.md §6) : NFKC, minuscules, sans accents, tirets et espaces réduits
à une espace, titres retirés."""

import re
import unicodedata

from ccm.config import NomsConfig
from ccm.ingest.racines import sans_accents


def norme(nom: str, cfg: NomsConfig) -> str:
    mots = re.sub(r"[-‐–\s]+", " ", sans_accents(unicodedata.normalize("NFKC", nom).casefold()))
    mots = mots.split()
    while len(mots) > 1 and mots[0].rstrip(".") in cfg.titres:
        mots.pop(0)
    return " ".join(mots)
