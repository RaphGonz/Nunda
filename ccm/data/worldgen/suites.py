"""Suites de référence du corpus synthétique niveau 0 (SPEC.md §10, « Ordre des suites de
référence ») pour toutes ses questions, et contrôle T10 (§14) : chaque pas de chaque suite
est autorisé par son masque, et l'automate accepte la suite.

Lit `<corpus>/<partie>/<dossier>/verite.json` et `questions.json` (`corpus.py`), construit
le stock de référence, l'exemple et la cible de chaque question (`cibles.py`), en mode
citation et, si la question a une synthèse, en mode synthèse (vocabulaire V provisoire :
mots des synthèses de référence du dossier, comme T4). Écrit `cibles.json` dans chaque
dossier (aucune chaîne de nom : pas, jetons et mots de synthèse) et `<corpus>/cibles.json`
(bilan par partie et par type ; refus avec leur premier pas interdit).

    uv run python -m ccm.data.worldgen.suites runs/corpus/niveau0 [processus]
"""

import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from pydantic import TypeAdapter

from ccm.config import load_config
from ccm.data.worldgen.cibles import cible_de_reference, exemple_de_reference
from ccm.data.worldgen.pieces import Dossier
from ccm.data.worldgen.questions import Question
from ccm.eval.equivariance import stock_de_reference
from ccm.grammar.automaton import Automate, Contexte
from ccm.grammar.lexicon import mots

QUESTIONS = TypeAdapter(list[Question])


def premier_refus(ctx: Contexte, suite: list[str], cfg, synthese: bool) -> str | None:
    """T10 : None si chaque pas est dans son masque et la suite finie ; sinon le refus."""
    a = Automate(ctx, cfg, synthese)
    for k, pas in enumerate(suite):
        if pas not in a.autorises():
            return f"pas {k} {pas!r} hors du masque à l'état {a.etat}"
        a.avancer(pas)
    return None if a.fini else "suite non finie"


def suites_du_dossier(dossier_dir: Path) -> dict:
    cfg, gcfg = load_config("ingest"), load_config("grammar")
    d = Dossier.model_validate_json((dossier_dir / "verite.json").read_text(encoding="utf-8"))
    questions = QUESTIONS.validate_json((dossier_dir / "questions.json").read_bytes())
    con = stock_de_reference(d, cfg)
    v = frozenset(m.lower() for q in questions for ph in q.synthese for e in ph.elements
                  for m in mots(e.mots))  # fmt: skip
    cibles, compte, refus = [], Counter(), []
    for q in questions:
        ex, valeurs = exemple_de_reference(d, q, con, cfg)
        ctx = Contexte.depuis_exemple(ex, valeurs, cfg.conflits.negation, v)
        out = dict(id=q.id, type=q.type, citation=None, synthese=None)
        for synthese in (False, True) if q.synthese else (False,):
            mode = "synthese" if synthese else "citation"
            try:
                suite = cible_de_reference(d, q, con, ex, cfg, synthese=synthese)
                pas_max = gcfg.pas_max_synthese if synthese else gcfg.pas_max
                r = premier_refus(ctx, suite, gcfg, synthese)
                if r is None and len(suite) > pas_max:
                    r = f"{len(suite)} pas, limite {pas_max}"
            except Exception as e:  # construction impossible : compté comme un refus
                suite, r = None, f"construction : {type(e).__name__}: {e}"
            compte[f"{q.type}|{mode}"] += 1
            if r is None:
                compte[f"{q.type}|{mode}|acceptees"] += 1
                out[mode] = suite
            else:
                refus.append(dict(id=q.id, type=q.type, mode=mode, refus=r))
        cibles.append(out)
    con.close()
    texte = json.dumps(cibles, ensure_ascii=False, indent=1)
    (dossier_dir / "cibles.json").write_text(texte, encoding="utf-8")
    return dict(compte=compte, refus=refus)


def main(corpus: Path, processus: int | None = None) -> dict:
    t0 = time.perf_counter()
    bilan: dict = {}
    for partie in ("entrainement", "validation", "test"):
        dossiers = sorted(p for p in (corpus / partie).iterdir() if p.is_dir())
        compte, refus = Counter(), []
        with ProcessPoolExecutor(processus) as ex:
            for r in ex.map(suites_du_dossier, dossiers, chunksize=4):
                compte.update(r["compte"])
                refus += r["refus"]
        par_mode = Counter()
        for k, n in compte.items():
            t = k.split("|")
            par_mode[f"{t[1]}|{'acceptees' if len(t) == 3 else 'suites'}"] += n
        bilan[partie] = dict(dossiers=len(dossiers), modes=dict(sorted(par_mode.items())),
                             types=dict(sorted(compte.items())), refus=refus)  # fmt: skip
    bilan["secondes"] = round(time.perf_counter() - t0)
    texte = json.dumps(bilan, ensure_ascii=False, indent=1)
    (corpus / "cibles.json").write_text(texte, encoding="utf-8")
    return bilan


if __name__ == "__main__":
    b = main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else None)
    for partie in ("entrainement", "validation", "test"):
        print(partie, b[partie]["modes"], "refus", len(b[partie]["refus"]))
    print("secondes", b["secondes"])
