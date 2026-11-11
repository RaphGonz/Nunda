"""Source Légifrance et Judilibre du réglage fin (SPEC.md §12) : questions gardées du modèle
enseignant (`enseignant/questions.jsonl`), passages lus dans `droit.sqlite`.

Une question = un `Brut` : le passage vu par l'enseignant (une proposition par phrase), puis
`distracteurs` passages d'autres questions de la même source, tirés par la graine. Les
justificatives sont les numéros rendus par l'enseignant, dans son ordre ; ses connecteurs
sont gardés s'il y en a un de moins que de justificatives.

`python -m ccm.data.droit_questions` : remplit le cache de détection des noms
(`cache-zones-droit.sqlite`, chaîne française), à faire une fois avant l'entraînement."""

import json
import random
import sqlite3
from pathlib import Path

from ccm.config import DonneesConfig
from ccm.data.publics import Brut

QUESTIONS = Path("enseignant") / "questions.jsonl"
CACHE = "cache-zones-droit.sqlite"


def bruts(dcfg: DonneesConfig) -> list[Brut]:
    lignes = []
    with (dcfg.racine / QUESTIONS).open(encoding="utf-8") as f:
        for ligne in f:
            r = json.loads(ligne)
            if r.get("gardee"):
                lignes.append(r)
    chemin = (dcfg.racine / dcfg.stock_droit).as_posix()
    con = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    ids = sorted({i for r in lignes for i in r["prop_ids"]})
    textes = {}
    for k in range(0, len(ids), 900):
        lot = ids[k : k + 900]
        q = f"SELECT prop_id, texte FROM proposition WHERE prop_id IN ({','.join('?' * len(lot))})"
        textes.update(con.execute(q, lot))
    con.close()
    passages = [[textes[i] for i in r["prop_ids"]] for r in lignes]
    par_source: dict[str, list[int]] = {}
    for k, r in enumerate(lignes):
        par_source.setdefault(r["source"], []).append(k)

    rng, out = random.Random(dcfg.graine), []
    for k, r in enumerate(lignes):
        autres = par_source[r["source"]]
        choix: list[int] = []
        while len(choix) < min(dcfg.distracteurs, len(autres) - 1):
            c = autres[rng.randrange(len(autres))]
            if c != k and c not in choix:
                choix.append(c)
        s = r["sortie"]
        justifs = [(0, n - 1) for n in s["justificatives"]]
        conn = s["connecteurs"] if len(s["connecteurs"]) == len(justifs) - 1 else None
        out.append(Brut(f"droit-{r['piece']}-{k}", r["source"], "fr", s["question"].strip(),
                        [passages[k], *(passages[c] for c in choix)], justifs,
                        connecteurs=conn))  # fmt: skip
    return out


def remplir() -> int:
    from ccm.config import load_config
    from ccm.data.publics import remplir_cache, textes_de
    from ccm.ner.union import detecter

    dcfg, icfg = load_config("donnees"), load_config("ingest")
    gliner = icfg.detection.gliner.model_copy(update={"lot": dcfg.lot_gliner})
    icfg = icfg.model_copy(
        update={"detection": icfg.detection.model_copy(update={"gliner": gliner})}
    )
    textes = (t for b in bruts(dcfg) for t in textes_de(b))
    return remplir_cache(textes, dcfg.racine / CACHE, lambda ts: detecter(ts, icfg),
                         dcfg.lot_detection)  # fmt: skip


if __name__ == "__main__":
    print(remplir(), "textes détectés")
