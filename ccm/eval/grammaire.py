"""Mesure de l'automate (SPEC.md §2, seuil de phase 3 ; §14, T4) : suites de référence
acceptées, et décodages au hasard sous masque, tous valides.

Dossiers synthétiques d'entraînement (graines 0, 1, …) avec les mentions de référence ;
pour chaque question, son exemple et des décodages au hasard, en mode citation et en mode
synthèse (vocabulaire V provisoire : mots des synthèses de référence du dossier). Un
décodage est valide s'il finit par FIN dans la limite de pas, sans impasse, et si
l'automate relit la suite (`accepter`).

    uv run python -m ccm.eval.grammaire 100000 runs/grammaire/bilan.json
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

from ccm.config import load_config
from ccm.data.worldgen.cibles import cible_de_reference, exemple_de_reference
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.eval.equivariance import stock_de_reference
from ccm.grammar.automaton import Contexte, accepter, decoder_au_hasard
from ccm.grammar.lexicon import mots


def main(total: int, sortie: Path, par_question: int = 10) -> dict:
    cfg, gcfg, wcfg = load_config("ingest"), load_config("grammar"), load_config("worldgen")
    n: Counter = Counter()
    longueurs: Counter = Counter()
    t0, i = time.perf_counter(), 0
    while n["decodages"] < total:
        d = rediger_dossier(generer_monde(i, "entrainement", wcfg, frozenset()), wcfg)
        questions = poser_questions(d, wcfg)
        con = stock_de_reference(d, cfg)
        v = frozenset(m.lower() for q in questions for ph in q.synthese for e in ph.elements
                      for m in mots(e.mots))  # fmt: skip
        for q in questions:
            ex, valeurs = exemple_de_reference(d, q, con, cfg)
            ctx = Contexte.depuis_exemple(ex, valeurs, cfg.conflits.negation, v)
            for synthese in (False, True):
                ref = cible_de_reference(d, q, con, ex, cfg, synthese=synthese)
                n["references"] += 1
                n["references_acceptees"] += accepter(ctx, ref, gcfg, synthese)
                pas_max = gcfg.pas_max_synthese if synthese else gcfg.pas_max
                n["references_dans_la_limite"] += len(ref) <= pas_max
                for g in range(par_question):
                    try:
                        s = decoder_au_hasard(ctx, gcfg, f"{i}:{q.id}:{g}", synthese)
                    except RuntimeError:
                        n["impasses"] += 1
                        continue
                    n["decodages"] += 1
                    n["valides"] += (
                        s[-1] == "FIN" and len(s) <= pas_max and accepter(ctx, s, gcfg, synthese)
                    )
                    longueurs[f"{'synthese' if synthese else 'citation'}|max"] = max(
                        longueurs[f"{'synthese' if synthese else 'citation'}|max"], len(s)
                    )
        con.close()
        i += 1
    bilan = dict(compte=dict(n), longueurs=dict(longueurs), dossiers=i,
                 secondes=round(time.perf_counter() - t0))  # fmt: skip
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")
    return bilan


if __name__ == "__main__":
    print(json.dumps(main(int(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False, indent=1))
