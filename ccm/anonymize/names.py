"""Norme d'un nom et nom de famille (SPEC.md §6).

Norme : NFKC, minuscules, sans accents, tirets et espaces réduits à une espace, titres
retirés. Nom de famille d'un nom PER : les mots tout en majuscules (« DUPONT Jean-Pierre »,
« DA SILVA Ana ») ; sinon le dernier mot, avec ses particules. Un jeu d'initiales
(« J.-P. », « JP », « L.M. ») n'a pas de nom de famille.
"""

import re
import unicodedata

from ccm.config import NomsConfig
from ccm.ingest.racines import sans_accents

_INITIALES = re.compile(r"(?:[A-Z]\.?-?){1,3}")


def norme(nom: str, cfg: NomsConfig) -> str:
    mots = re.sub(r"[-‐–\s]+", " ", sans_accents(unicodedata.normalize("NFKC", nom).casefold()))
    mots = mots.split()
    while len(mots) > 1 and mots[0].rstrip(".") in cfg.titres:
        mots.pop(0)
    return " ".join(mots)


def nom_famille(surface: str, cfg: NomsConfig) -> str | None:
    """Norme du nom de famille d'une mention PER ; None pour un jeu d'initiales."""
    mots = surface.split()
    while len(mots) > 1 and norme(mots[0], cfg).rstrip(".") in cfg.titres:
        mots.pop(0)
    if len(mots) == 1 and _INITIALES.fullmatch(mots[0]):
        return None
    caps = [k for k, m in enumerate(mots) if len(m) > 1 and m.isupper() and _lettres(m)]
    if caps and len(caps) < len(mots):
        famille = mots[caps[0] : caps[-1] + 1]
    else:
        k = len(mots) - 1
        while k > 0 and norme(mots[k - 1], cfg) in cfg.particules:
            k -= 1
        famille = mots[k:]
    return norme(" ".join(famille), cfg) or None


def _lettres(mot: str) -> bool:
    return re.sub(r"[-'’]", "", mot).isalpha()
