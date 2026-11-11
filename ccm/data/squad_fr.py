"""Jeux au format SQuAD (SPEC.md §12).

`sans_reponse` : SQuAD 2.0, questions sans réponse → ABSTENTION sur leur paragraphe.
`avec_reponse` : FQuAD, PIAF → la phrase qui contient l'extrait = CITE, plus des paragraphes
du même article comme distracteurs. À ne lancer qu'une fois la licence du jeu claire.
"""

import json
import random
from collections.abc import Iterator
from pathlib import Path

from ccm.data.publics import Brut, phrases


def sans_reponse(chemin: Path, langue: str = "en") -> Iterator[Brut]:
    jeu = json.loads(chemin.read_text(encoding="utf-8"))
    for art in jeu["data"]:
        for par in art["paragraphs"]:
            qas = [q for q in par["qas"] if q.get("is_impossible")]
            if not qas:
                continue
            ps = [p for _, p in phrases(par["context"], langue)]
            for q in qas:
                yield Brut(f"squad-{q['id']}", "squad", langue, q["question"].strip(), [ps],
                           abstention=True, temoins=[art["title"].replace("_", " ")])  # fmt: skip


def avec_reponse(chemin: Path, origine: str, langue: str, distracteurs: int, graine: int
                 ) -> Iterator[Brut]:  # fmt: skip
    jeu = json.loads(chemin.read_text(encoding="utf-8"))
    rng = random.Random(graine)
    for art in jeu["data"]:
        lus = [phrases(par["context"], langue) for par in art["paragraphs"]]
        for i, par in enumerate(art["paragraphs"]):
            autres = [k for k in range(len(lus)) if k != i]
            for q in par["qas"]:
                if not q.get("answers"):
                    continue
                debut = q["answers"][0]["answer_start"]
                j = max((j for j, (d, _) in enumerate(lus[i]) if d <= debut), default=0)
                choix = rng.sample(autres, min(distracteurs, len(autres)))
                paragraphes = [[p for _, p in lus[k]] for k in [i, *choix]]
                yield Brut(f"{origine}-{q['id']}", origine, langue, q["question"].strip(),
                           paragraphes, [(0, j)],
                           temoins=[art["title"].replace("_", " ")])  # fmt: skip
