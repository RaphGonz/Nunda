"""Norme d'un nom et analyse d'un nom PER (SPEC.md §6).

Norme : NFKC, minuscules, sans accents, tirets et espaces réduits à une espace, titres
retirés. Nom de famille d'un nom PER : les mots tout en majuscules (« DUPONT Jean-Pierre »,
« DA SILVA Ana ») ; sinon le dernier mot, avec ses particules. Les autres mots sont les
prénoms. Un mot seul en minuscules a un rôle inconnu. Une chaîne de 1 à 3 majuscules, avec
ou sans points (« J.-P. », « JP », « L.M. »), est un jeu d'initiales, sans nom de famille.
"""

import re
import unicodedata
from dataclasses import dataclass

from ccm.config import NomsConfig
from ccm.ingest.racines import sans_accents

_INITIALES = re.compile(r"(?:[A-Z]\.?-?){1,3}")


@dataclass(frozen=True)
class AnalyseNom:
    famille: str | None  # norme du nom de famille
    prenoms: tuple[str, ...]  # normes des prénoms, sans points
    initiales: str | None  # jeu d'initiales, en majuscules (« JP »)


def norme(nom: str, cfg: NomsConfig) -> str:
    mots = re.sub(r"[-‐–\s]+", " ", sans_accents(unicodedata.normalize("NFKC", nom).casefold()))
    mots = mots.split()
    while len(mots) > 1 and mots[0].rstrip(".") in cfg.titres:
        mots.pop(0)
    return " ".join(mots)


def analyser(surface: str, cfg: NomsConfig) -> AnalyseNom:
    """Prénoms, nom de famille ou jeu d'initiales d'une mention PER."""
    mots = surface.split()
    while len(mots) > 1 and norme(mots[0], cfg).rstrip(".") in cfg.titres:
        mots.pop(0)
    if len(mots) == 1 and _INITIALES.fullmatch(mots[0]):
        return AnalyseNom(None, (), re.sub(r"[.-]", "", mots[0]))
    if len(mots) == 1 and mots[0].islower():
        return AnalyseNom(None, (), None)
    caps = [k for k, m in enumerate(mots) if len(m) > 1 and m.isupper() and _lettres(m)]
    if caps and len(caps) < len(mots):
        a, b = caps[0], caps[-1] + 1
    else:
        a, b = len(mots) - 1, len(mots)
        while a > 0 and norme(mots[a - 1], cfg) in cfg.particules:
            a -= 1
    prenoms = norme(" ".join(mots[:a] + mots[b:]), cfg).replace(".", "").split()
    return AnalyseNom(norme(" ".join(mots[a:b]), cfg) or None, tuple(prenoms), None)


def nom_famille(surface: str, cfg: NomsConfig) -> str | None:
    """Norme du nom de famille d'une mention PER ; None pour un jeu d'initiales."""
    return analyser(surface, cfg).famille


def _lettres(mot: str) -> bool:
    return re.sub(r"[-'’]", "", mot).isalpha()
