"""Racines des mots d'un texte : signature des conflits (SPEC.md §5) et index BM25 (§7).

Minuscules, mots vides retirés, racines Snowball, puis accents retirés.
"""

import re
import unicodedata
from functools import cache

import Stemmer

from ccm.config import RacinesConfig

_MOT = re.compile(r"\w+")


@cache
def _stemmer(langue: str) -> Stemmer.Stemmer:
    return Stemmer.Stemmer(langue)


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if not unicodedata.combining(c))


def racines(texte: str, cfg: RacinesConfig) -> list[str]:
    vides = set(cfg.mots_vides)
    mots = [m for m in _MOT.findall(texte.casefold()) if m not in vides]
    return [sans_accents(r) for r in _stemmer(cfg.langue).stemWords(mots)]
