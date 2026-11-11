"""FinQA (SPEC.md §12) : programme de référence → CALCUL postfixe ; seuls restent les programmes
sans constante, avec +, −, ×, ÷. Une phrase ou une rangée du tableau = une proposition ; les
`gold_inds` sont les justificatives."""

import json
import re
from pathlib import Path

from ccm.data.publics import Brut
from ccm.schema import GenreProposition

_OPS = {"add": "+", "subtract": "−", "multiply": "×", "divide": "÷"}
_ETAPE = re.compile(r"(\w+)\(([^,()]+),\s*([^,()]+)\)")
_NOMBRE = re.compile(r"\d+(?:\.\d+)?")
GENRES = [GenreProposition.PHRASE, GenreProposition.LIGNE_TABLEAU]


class HorsChamp(ValueError):
    """Programme écarté par la règle du §12."""


def postfixe(programme: str) -> list[str]:
    """« subtract(5829, 5735), divide(#0, 5735) » → 5829 5735 − 5735 ÷."""
    etapes: list[list[str]] = []
    trouvees = _ETAPE.findall(programme)
    if not trouvees:
        raise HorsChamp("programme illisible")
    for op, a, b in trouvees:
        if op not in _OPS:
            raise HorsChamp("opération hors de + − × ÷")
        suite: list[str] = []
        for x in (a.strip(), b.strip()):
            if x.startswith("#"):
                suite += etapes[int(x[1:])]
            elif x.startswith("const_"):
                raise HorsChamp("constante")
            elif _NOMBRE.fullmatch(x.rstrip("%")):
                suite.append(x.rstrip("%"))
            else:
                raise HorsChamp("opérande non numérique")
        etapes.append([*suite, _OPS[op]])
    return etapes[-1]


def lire(chemin: Path) -> tuple[list[Brut], dict[str, int]]:
    """Exemples gardés et comptes des programmes écartés par raison."""
    gardes, ecartes = [], {}
    for n, d in enumerate(json.loads(chemin.read_text(encoding="utf-8"))):
        qa = d["qa"]
        try:
            suite = postfixe(qa["program"])
        except HorsChamp as e:
            ecartes[str(e)] = ecartes.get(str(e), 0) + 1
            continue
        textes = [*d["pre_text"], *d["post_text"]]
        # Phrases vides ou réduites à un point : pas de proposition, indices conservés.
        indices = {i: k for k, i in enumerate(i for i, t in enumerate(textes) if t.strip(" ."))}
        paragraphes = [[t.strip() for t in textes if t.strip(" .")],
                       [" | ".join(c.strip() for c in r) for r in d["table"]]]  # fmt: skip
        justifs = []
        for cle in qa["gold_inds"]:
            genre, _, i = cle.partition("_")
            if genre == "table":
                justifs.append((1, int(i)))
            else:
                justifs.append((0, indices.get(int(i), len(textes))))
        gardes.append(Brut(f"finqa-{n}", "finqa", "en", qa["question"].strip(), paragraphes,
                           justifs, postfixe=suite, genres=GENRES))  # fmt: skip
    return gardes, ecartes
