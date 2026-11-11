"""Phrases et fenêtres d'un document (SPEC.md §12) : fenêtres coupées en fin de phrase.

Les phrases viennent de `phrases` (pysbd, `publics.py`), ligne par ligne : pysbd est lent sur
un très long texte. Une fenêtre est une suite de phrases voisines dont le compte de jetons,
majoré par la somme des jetons des phrases plus un par phrase (le blanc qui les sépare), tient
dans la limite. Une phrase plus longue que la limite est coupée entre deux mots.

Le BPE de B n'existe pas encore (il s'entraîne sur le corpus anonymisé) : on compte avec le
tokenizer de SmolLM2 (`ccm.train.a0._tokenizer`). Le chargeur de B recoupera au besoin.
"""

import re
from collections.abc import Callable
from functools import cache

from ccm.data.publics import phrases

Compteur = Callable[[list[str]], list[int]]


def compter_mots(textes: list[str]) -> list[int]:
    """Un jeton par mot : compteur des tests."""
    return [len(t.split()) for t in textes]


@cache
def _smollm2():
    from ccm.train.a0 import _tokenizer

    return _tokenizer()[1]


def compter_smollm2(textes: list[str]) -> list[int]:
    decouper = _smollm2()
    return [len(decouper(t)) for t in textes]


def compteur(nom: str) -> Compteur:
    return {"mots": compter_mots, "smollm2": compter_smollm2}[nom]


def _couper(texte: str, debut: int, fin: int, compter: Compteur, limite: int):
    """Morceaux (début, fin) d'une phrase trop longue, coupés entre deux mots."""
    mots = [(debut + m.start(), debut + m.end()) for m in re.finditer(r"\S+", texte[debut:fin])]
    jetons = compter([texte[a:b] for a, b in mots])
    out, d, total, prec = [], None, 0, debut
    for (a, b), j in zip(mots, jetons, strict=True):
        j = min(j + 1, limite)
        if d is not None and total + j > limite:
            out.append((d, prec))
            d, total = None, 0
        if d is None:
            d = a
        total, prec = total + j, b
    if d is not None:
        out.append((d, prec))
    return out


def decouper_document(texte: str, langue: str, compter: Compteur, limite: int
                      ) -> tuple[list[tuple[int, int]], list[tuple[int, int, int]]]:  # fmt: skip
    """(phrases (début, fin), fenêtres (première phrase, phrase après la dernière, jetons))."""
    spans: list[tuple[int, int]] = []
    k = 0
    for ligne in texte.split("\n"):
        for d, p in phrases(ligne, langue) if ligne.strip() else []:
            spans.append((k + d, k + d + len(p)))
        k += len(ligne) + 1
    jetons = compter([texte[a:b] for a, b in spans])
    phr: list[tuple[int, int]] = []
    tj: list[int] = []
    for (a, b), j in zip(spans, jetons, strict=True):
        if j + 1 > limite:
            morceaux = _couper(texte, a, b, compter, limite)
            phr += morceaux
            tj += [min(x + 1, limite) for x in compter([texte[x:y] for x, y in morceaux])]
        else:
            phr.append((a, b))
            tj.append(j + 1)
    fen, debut, total = [], 0, 0
    for i, j in enumerate(tj):
        if i > debut and total + j > limite:
            fen.append((debut, i, total))
            debut, total = i, 0
        total += j
    if phr:
        fen.append((debut, len(phr), total))
    return phr, fen
