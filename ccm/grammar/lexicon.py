"""Lexique de sortie (SPEC.md §10, §10 bis) : 25 jetons, 30 avec la synthèse.

Un pas de sortie est un jeton du lexique, un pointeur (« P:k », « M:k.j », « N:k.j ») ou,
dans une synthèse, un mot (« W:mot »).
"""

import re

from ccm.schema import LEXIQUE, LEXIQUE_SYNTHESE

LEXIQUE_COMPLET = LEXIQUE + LEXIQUE_SYNTHESE
CONNECTEURS = ("ET", "MAIS", "DONC", "EN_REVANCHE", "PAR_AILLEURS")
OPERATEURS = ("+", "−", "×", "÷", "MIN", "MAX")
NAVIGATION = ("OUVRIR", "RETOUR")  # réservés, toujours masqués en v1

_MOT = re.compile(r"\w+['’]?|[^\w\s]")


def mots(texte: str) -> list[str]:
    """Mots d'un texte libre de synthèse : « l'heure. » → « l' », « heure », « . »."""
    return _MOT.findall(texte)
