"""Préchargement des exemples de réglage fin de A0 (SPEC.md §12, §13) : les époques du
chargeur sont construites d'avance, en plusieurs processus, et écrites par paquets de
`PAQUET` places. L'entraînement lit ensuite les paquets sans charger les sources.

Chaque époque garde ses propres tirages (genres, indices, contexte), comme si le chargeur
tournait pendant l'entraînement : `Chargeur.exemple(source, j, epoque, place)` ne dépend que
de la graine. Une relance saute les paquets déjà écrits.

`python -m ccm.train.precharger [epoques] [processus]`"""

import json
import os
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PAQUET = 1000
_CH = None
_PLANS: dict[int, list] = {}


def sortie() -> Path:
    from ccm.config import load_config

    return load_config("donnees").racine / "tirages" / "a0"


def _chargeur():
    global _CH
    if _CH is None:
        from ccm.config import load_config
        from ccm.train.a0 import _tokenizer
        from ccm.train.chargeur import Chargeur, sources_disponibles

        voc, decouper = _tokenizer()
        icfg = load_config("ingest")
        corpus = Path(load_config("worldgen").redaction.sortie) / "entrainement"
        if not corpus.exists():
            raise FileNotFoundError(f"{corpus} : lancer `ccm corpus --partie entrainement`")
        sources = sources_disponibles(load_config("donnees"), icfg, corpus)
        _CH = Chargeur(sources, load_config("finetune").chargeur, icfg, load_config("search"),
                       load_config("grammar"), voc, decouper)  # fmt: skip
    return _CH


def _paquet(epoque: int, debut: int, chemin: str) -> dict:
    ch = _chargeur()
    plan = _PLANS.setdefault(epoque, ch.plan(epoque))
    t0, avant = time.time(), ch.bilan.copy()
    tirages = []
    for place in range(debut, min(debut + PAQUET, len(plan))):
        s, j = plan[place]
        t = ch.exemple(s, j, epoque, place)
        if t is not None:
            tirages.append(t)
    p = Path(chemin)
    p.with_suffix(".tmp").write_bytes(pickle.dumps(tirages, protocol=pickle.HIGHEST_PROTOCOL))
    p.with_suffix(".tmp").replace(p)
    return {"paquet": p.name, "epoque": epoque, "exemples": len(tirages),
            "secondes": time.time() - t0, "bilan": dict(ch.bilan - avant)}  # fmt: skip


def precharger(epoques: int = 3, processus: int = 8) -> None:
    from ccm.config import load_config

    n = load_config("finetune").chargeur.exemples_par_epoque
    racine = sortie()
    taches = []
    for e in range(epoques):
        (racine / f"epoque-{e}").mkdir(parents=True, exist_ok=True)
        for debut in range(0, n, PAQUET):
            p = racine / f"epoque-{e}" / f"{debut:07d}.pkl"
            if not p.exists():
                taches.append((e, debut, str(p)))
    print(f"{len(taches)} paquets à écrire dans {racine}", flush=True)
    t0 = time.time()
    with (ProcessPoolExecutor(processus) as ex,
          (racine / "bilan.jsonl").open("a", encoding="utf-8") as bilan):  # fmt: skip
        futurs = [ex.submit(_paquet, *t) for t in taches]
        for k, f in enumerate(as_completed(futurs), 1):
            r = f.result()
            bilan.write(json.dumps(r) + "\n")
            bilan.flush()
            reste = (time.time() - t0) / k * (len(taches) - k)
            print(f"{k}/{len(taches)} {r['paquet']} (époque {r['epoque']}) ; "
                  f"reste environ {reste / 3600:.1f} h", flush=True)  # fmt: skip


def lire(epoque: int, racine: Path | None = None):
    """Exemples préchargés d'une époque, dans l'ordre des places."""
    d = (racine or sortie()) / f"epoque-{epoque}"
    for p in sorted(d.glob("*.pkl")):
        yield from pickle.loads(p.read_bytes())


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    precharger(*map(int, sys.argv[1:]))
