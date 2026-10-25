"""Mesure de la recherche (SPEC.md §7 et §14) : rappel des propositions justificatives
dans le budget, par type de question.

Chaque dossier est ingéré avec la vraie chaîne (stock gardé dans la sortie, réutilisé s'il
existe), puis chaque question est lue avec les vrais détecteurs (`lire_message`) et
cherchée. Une justificative est la première ligne de chaque étape de la vérité terrain
(`Question.justificatives`) ; elle est trouvée si sa proposition, ou la proposition gardée
de son groupe de doublons, est dans le contexte rendu. Rappel « étape » : une des lignes
équivalentes de l'étape suffit. Une ligne sans proposition (texte non retrouvé à
l'ingestion) compte comme manquée. Dialogue : les lignes citées par la réponse précédente
entrent comme `citees`. Les questions sans étape (abstention) ne comptent pas.

    python -m ccm.eval.recherche runs/corpus/niveau0/validation runs/recherche/validation
    python -m ccm.eval.recherche runs/corpus/niveau0/validation runs/recherche/validation : 1000

(3e argument : tranche de dossiers, « : » pour tous ; 4e : budget de jetons plus serré que
la config, pour juger le classement)
"""

import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ccm.anonymize.exemple import lire_message
from ccm.config import load_config
from ccm.data.worldgen.pieces import Dossier
from ccm.data.worldgen.questions import Question
from ccm.eval.conflits import _lignes_props
from ccm.ingest.pipeline import fichiers_pdf, ingerer_fichiers
from ccm.schema import ouvrir_stock
from ccm.search.bm25 import charger_index, construire_index, dossier_index
from ccm.search.retrieve import chercher


def mesurer_dossier(dossier: Path, sortie: Path, jetons: int | None = None) -> dict:
    cfg, cfg_s = load_config("ingest"), load_config("search")
    d = Dossier.model_validate_json((dossier / "verite.json").read_text(encoding="utf-8"))
    stock = sortie / f"{dossier.name}.sqlite"
    neuf = not stock.exists()
    con = ouvrir_stock(stock)
    if neuf:
        ingerer_fichiers(con, fichiers_pdf([dossier]), cfg)
        con.commit()
    construire_index(con, dossier_index(stock), cfg, cfg_s)
    index = charger_index(dossier_index(stock))
    lignes = _lignes_props(con, d)
    garde = dict(con.execute("SELECT prop_id, COALESCE(groupe_doublon, prop_id) FROM proposition"))

    def prop(ref: str) -> int | None:
        piece, i = ref.split(":")
        p = lignes.get((piece, int(i)))
        return None if p is None else garde[p]

    n: Counter = Counter()
    manques = []
    qs = json.loads((dossier / "questions.json").read_text(encoding="utf-8"))
    for q in map(Question.model_validate, qs):
        if not q.etapes:
            continue
        t0 = time.perf_counter()
        precedentes = [lire_message(t.texte, con, cfg) for t in q.historique
                       if t.role == "UTILISATEUR" and t.texte]  # fmt: skip
        modele = [t for t in q.historique if t.role == "MODELE"]
        citees = frozenset(
            p for p in map(prop, modele[-1].lignes if modele else ()) if p is not None
        )
        res = chercher(con, index, lire_message(q.message.texte, con, cfg), cfg_s, cfg,
                       precedentes=precedentes, citees=citees, jetons_max=jetons)  # fmt: skip
        n[f"{q.type}|duree"] += time.perf_counter() - t0
        rendues = set(res.prop_ids)
        n[f"{q.type}|questions"] += 1
        n[f"{q.type}|propositions"] += len(rendues)
        n[f"{q.type}|stock"] += len(index.prop_ids)
        n[f"{q.type}|jetons"] += res.jetons
        n[f"{q.type}|sans_nom"] += not res.noms
        for e in q.etapes:
            p = prop(e.lignes[0])
            n[f"{q.type}|justificatives"] += 1
            n[f"{q.type}|non_ingerees"] += p is None
            n[f"{q.type}|trouvees"] += p in rendues
            n[f"{q.type}|etapes_trouvees"] += any(prop(x) in rendues for x in e.lignes)
            if p not in rendues:
                manques.append(dict(question=q.id, texte=q.message.texte, ligne=e.lignes[0],
                                    prop_id=p, noms=res.noms))  # fmt: skip
    con.close()
    return dict(dossier=dossier.name, compte=dict(n), manques=manques)


def _bilan(rs: list[dict]) -> dict:
    n: Counter = Counter()
    for r in rs:
        n.update(r["compte"])
    types = sorted({k.split("|")[0] for k in n})
    out = {}
    for t in [*types, "TOUS"]:
        us = types if t == "TOUS" else [t]

        def c(k, us=us):
            return sum(n[f"{u}|{k}"] for u in us)

        j, q = c("justificatives"), c("questions")
        out[t] = dict(
            questions=q,
            justificatives=j,
            rappel=round(c("trouvees") / j, 4) if j else None,
            rappel_etapes=round(c("etapes_trouvees") / j, 4) if j else None,
            non_ingerees=c("non_ingerees"),
            sans_nom=c("sans_nom"),
            propositions_moy=round(c("propositions") / q, 1) if q else None,
            part_du_stock=round(c("propositions") / c("stock"), 3) if q else None,
            jetons_moy=round(c("jetons") / q, 1) if q else None,
            ms_par_question=round(1000 * c("duree") / q, 1) if q else None,
        )
    return out


def main(
    source: Path,
    sortie: Path,
    tranche: slice = slice(None),
    processus: int = 3,
    jetons: int | None = None,
) -> dict:
    sortie.mkdir(parents=True, exist_ok=True)
    dossiers = sorted(p for p in source.iterdir() if (p / "verite.json").exists())[tranche]
    with ProcessPoolExecutor(processus) as ex:
        rs = list(ex.map(mesurer_dossier, dossiers, [sortie] * len(dossiers),
                         [jetons] * len(dossiers)))  # fmt: skip
    bilan = _bilan(rs)
    (sortie / f"bilan{'-' + str(jetons) if jetons else ''}.json").write_text(
        json.dumps(dict(bilan=bilan, dossiers=rs), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return bilan


if __name__ == "__main__":
    # Tranche des dossiers : « 20 » (les 20 premiers) ou « 20:60 » ; budget de jetons en 4e.
    t = [int(x) if x else None for x in sys.argv[3].split(":")] if len(sys.argv) > 3 else []
    tranche = slice(*t) if len(t) == 2 else slice(t[0] if t else None)
    print(
        json.dumps(
            main(
                Path(sys.argv[1]),
                Path(sys.argv[2]),
                tranche,
                jetons=int(sys.argv[4]) if len(sys.argv) > 4 else None,
            ),  # fmt: skip
            ensure_ascii=False,
            indent=1,
        )
    )
