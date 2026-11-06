"""Préchargement des exemples de réglage fin de A0 (SPEC.md §12, §13) : les époques du
chargeur sont construites d'avance et écrites sur le disque ; l'entraînement les lit sans
charger les sources.

Une commande par source : ses processus ne chargent que cette source (la RAM ne suffit pas
pour toutes les sources dans chaque processus). Le plan d'une époque est celui du chargeur
avec toutes les sources du mélange ; la place et le tirage d'un exemple ne dépendent que de
la graine et de la taille de sa propre source (`Chargeur.plan`, `Chargeur.exemple`). Une
source peut donc être préchargée plus tard sans rien refaire. Une relance saute les paquets
déjà écrits.

`python -m ccm.train.precharger <source> [processus] [epoques]`"""

import heapq
import json
import os
import pickle
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PAQUET = 1000
_CH = None
_PLANS: dict[int, list] = {}


class Absente:
    """Source du mélange chargée par un autre processus : seule sa part compte ici."""

    def __len__(self) -> int:
        return 1

    def cas(self, i: int):
        raise RuntimeError("source chargée par un autre processus")


def sortie() -> Path:
    from ccm.config import load_config

    return load_config("donnees").racine / "tirages" / "a0"


def chargeur(source: str):
    """Chargeur de l'entraînement, avec la seule `source` chargée."""
    from ccm.config import load_config
    from ccm.train.a0 import _tokenizer
    from ccm.train.chargeur import Chargeur, sources_disponibles

    voc, decouper = _tokenizer()
    icfg, cfg = load_config("ingest"), load_config("finetune").chargeur
    corpus = Path(load_config("worldgen").redaction.sortie) / "entrainement"
    reelles = sources_disponibles(load_config("donnees"), icfg, corpus, seules={source})
    if source not in reelles:
        raise FileNotFoundError(f"source {source} absente du disque")
    sources = {s: reelles.get(s) or Absente() for s in cfg.poids}
    return Chargeur(sources, cfg, icfg, load_config("search"), load_config("grammar"), voc,
                    decouper)  # fmt: skip


def _paquet(source: str, epoque: int, places: list[int], chemin: str) -> dict:
    global _CH
    _CH = _CH or chargeur(source)
    plan = _PLANS.setdefault(epoque, _CH.plan(epoque))
    t0, avant = time.time(), _CH.bilan.copy()
    out = []
    for place in places:
        s, j = plan[place]
        out.append((place, _CH.exemple(s, j, epoque, place)))
    p = Path(chemin)
    p.with_suffix(".tmp").write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    p.with_suffix(".tmp").replace(p)
    return {"paquet": p.name, "epoque": epoque, "places": len(places),
            "exemples": sum(t is not None for _, t in out), "secondes": time.time() - t0,
            "bilan": dict(_CH.bilan - avant)}  # fmt: skip


def precharger(source: str, processus: int = 2, epoques: int = 3) -> None:
    racine = sortie()
    plan_de = chargeur_plan()
    taches = []
    for e in range(epoques):
        (racine / f"epoque-{e}").mkdir(parents=True, exist_ok=True)
        places = [i for i, (s, _) in enumerate(plan_de(e)) if s == source]
        for k in range(0, len(places), PAQUET):
            p = racine / f"epoque-{e}" / f"{source}-{k // PAQUET:04d}.pkl"
            if not p.exists():
                taches.append((source, e, places[k : k + PAQUET], str(p)))
    print(f"{source} : {len(taches)} paquets à écrire dans {racine}", flush=True)
    t0 = time.time()
    with (ProcessPoolExecutor(processus) as ex,
          (racine / f"bilan-{source}.jsonl").open("a", encoding="utf-8") as bilan):  # fmt: skip
        futurs = [ex.submit(_paquet, *t) for t in taches]
        for k, f in enumerate(as_completed(futurs), 1):
            r = f.result()
            bilan.write(json.dumps(r) + "\n")
            bilan.flush()
            reste = (time.time() - t0) / k * (len(taches) - k)
            print(f"{source} {k}/{len(taches)} {r['paquet']} (époque {r['epoque']}) ; "
                  f"reste environ {reste / 3600:.1f} h", flush=True)  # fmt: skip


def chargeur_plan():
    """Plan d'une époque sans charger de source (toutes `Absente`) : mêmes places."""
    from ccm.config import load_config
    from ccm.train.chargeur import Chargeur

    cfg = load_config("finetune").chargeur
    ch = Chargeur({s: Absente() for s in cfg.poids}, cfg, load_config("ingest"),
                  load_config("search"), load_config("grammar"), None, None)  # fmt: skip
    return ch.plan


def lire(epoque: int, racine: Path | None = None):
    """Exemples préchargés d'une époque (toutes sources), dans l'ordre des places. Fusion
    des paquets de chaque source : un seul paquet par source en mémoire."""
    d = (racine or sortie()) / f"epoque-{epoque}"
    par_source: dict[str, list[Path]] = {}
    for p in sorted(d.glob("*.pkl")):
        par_source.setdefault(p.stem.rsplit("-", 1)[0], []).append(p)
    attendus = Counter(s for s, _ in chargeur_plan()(epoque))
    for src, n in attendus.items():
        manque = -(-n // PAQUET) - len(par_source.get(src, []))
        if manque:
            raise FileNotFoundError(f"époque {epoque} : {manque} paquets {src} manquent dans {d}")

    def suite(chemins):
        for p in chemins:
            yield from pickle.loads(p.read_bytes())

    for _, t in heapq.merge(*map(suite, par_source.values()), key=lambda x: x[0]):
        if t is not None:
            yield t


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    source, *reste = sys.argv[1:]
    precharger(source, *map(int, reste))
