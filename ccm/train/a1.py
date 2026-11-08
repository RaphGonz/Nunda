"""Réglage fin de A1 (SPEC.md §13) : part du point de contrôle A0, sans l'en-tête [REL],
δ à zéro. Même boucle, même perte, mêmes points de contrôle que A0 (`ccm.train.a0`).

`python -m ccm.train.a1 essai [point_a0] [exemples] [pas]` : essai à blanc (§13, « Ordre de
lancement ») sur les exemples de l'essai de A0 (`runs/*-a0-essai/tirages.pkl`), en-tête
retiré, T ≤ 2 500 : δ = 0 rend la perte de A0 ; 200 pas, la perte baisse ; le point de
contrôle se recharge ; T1 (permutation des noms) mesuré. Dossier `runs/<date>-a1-essai/`.
`python -m ccm.train.a1 preparer [epoques] [processus]` : tirages préchargés de A0
(`tirages/a0/epoque-<e>`) → `tirages/a1/epoque-<e>` : en-tête retiré, T > 2 500 écarté (la
place reste, vide) ; `precharger.lire(e, racine)` les lit comme ceux de A0.
`python -m ccm.train.a1 debit [minutes]` : débit à pleine taille sur l'époque 0 de A1, et
durée des 2 époques (§13, « Ordre de lancement »). Dossier `runs/<date>-a1-debit/`."""

import dataclasses
import itertools
import json
import pickle
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import torch

from ccm.model.a1 import T_MAX, depuis_a0, optimiseur, sans_rel
from ccm.train.a0 import (
    SMOLLM,
    _dossier_run,
    _tokenizer,
    entrainer,
    ordonnanceur,
    pertes_eval,
    recharger,
    sauver,
)

RUNS = Path(__file__).resolve().parents[2] / "runs"
POINT_A0 = RUNS / "2026-11-06-a0" / "pas-018124.pt"
JETONS_LOT = 4000  # biais dense B × 15 × T × T par couche : moitié du lot de A0


def tirages_a1(tirages, voc):
    """Tirages de A0 → A1 : en-tête retiré ; ceux qui dépassent T_MAX sont écartés."""
    out = [dataclasses.replace(t, encodage=sans_rel(t.encodage, voc)) for t in tirages]
    return [t for t in out if len(t.encodage.input_ids) <= T_MAX]


def permuter(enc, rng):
    """T1 (§14) : renumérote les noms (name_idx, lignes et colonnes de NN) et les valeurs."""
    n, v = len(enc.NN), int(enc.val_idx.max()) + 1
    pn, pv = np.r_[0, 1 + rng.permutation(n - 1)], np.r_[0, 1 + rng.permutation(v - 1)]
    nn_ = np.zeros_like(enc.NN)
    nn_[np.ix_(pn, pn)] = enc.NN
    return dataclasses.replace(enc, name_idx=pn[enc.name_idx], val_idx=pv[enc.val_idx], NN=nn_)


@torch.no_grad()
def ecart_t1(modele, tirages, graine=0) -> float:
    rng, dev = np.random.default_rng(graine), modele.lex.weight.device
    modele.eval()
    ecart = 0.0
    for t in tirages:
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            a, b = modele(t.encodage).logits, modele(permuter(t.encodage, rng)).logits
        fini = torch.isfinite(a)
        ecart = max(ecart, (a[fini] - b[fini]).abs().max().item())
    modele.train()
    return ecart


def essai(point_a0: str = str(POINT_A0), exemples: int = 1000, pas: int = 200,
          accumulation: int = 16, echauffement: int = 500) -> dict:  # fmt: skip
    from ccm.model.a1 import charger_smollm_a1

    run = _dossier_run("a1-essai")
    shutil.copy(RUNS.parent / "configs" / "model_a1.yaml", run / "model_a1.yaml")
    (run / "point_a0.txt").write_text(str(point_a0))
    metrics = (run / "metrics.jsonl").open("a", encoding="utf-8")
    ecrire = lambda **k: (metrics.write(json.dumps(k) + "\n"), metrics.flush())  # noqa: E731
    voc, _ = _tokenizer()
    source = sorted(RUNS.glob("*-a0-essai/tirages.pkl"))[-1]
    brut = pickle.loads(source.read_bytes())[:exemples]
    tirages = tirages_a1(brut, voc)
    longueurs = [len(t.encodage.input_ids) for t in tirages]
    ecrire(etape="donnees", source=str(source), exemples_a0=len(brut), exemples=len(tirages),
           jetons_moyen=sum(longueurs) / len(longueurs), jetons_max=max(longueurs))  # fmt: skip
    print(f"{len(tirages)} exemples sur {len(brut)} (T ≤ {T_MAX}) ; T moyen "
          f"{sum(longueurs) / len(longueurs):.0f}", flush=True)  # fmt: skip

    torch.manual_seed(0)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modele = charger_smollm_a1(voc, SMOLLM).to(dev)
    pas_a0 = depuis_a0(modele, Path(point_a0))
    opt = optimiseur(modele)
    sched = ordonnanceur(opt, echauffement)
    temoins = tirages[:8]

    # 0. δ = 0 : A1 calcule A0 (même point de contrôle) sur une entrée sans en-tête.
    depart = pertes_eval(modele, temoins)
    from ccm.model.a0 import charger_smollm

    a0 = charger_smollm(voc, SMOLLM).to(dev)
    recharger(Path(point_a0), a0)
    sans_biais = pertes_eval(a0, temoins)
    del a0
    ecart_depart = max(abs(a - b) for a, b in zip(depart, sans_biais, strict=True))
    t1_depart = ecart_t1(modele, temoins)
    ecrire(etape="depart", pas_a0=pas_a0, pertes=depart, ecart_a0=ecart_depart, t1=t1_depart)
    print(f"départ (A0, pas {pas_a0}) : écart δ=0 / A0 {ecart_depart:.2e}", flush=True)

    # 1. Essai à blanc.
    if dev == "cuda":
        torch.cuda.reset_peak_memory_stats()
    t0 = time.time()

    def journal(i, x):
        ecrire(etape="essai", pas=i, perte=x, lr=sched.get_last_lr()[0], secondes=time.time() - t0,
               delta_max=modele.delta.abs().max().item())  # fmt: skip
        if i % 10 == 0 or i == pas - 1:
            print(f"pas {i} perte {x:.4f} |δ|max {modele.delta.abs().max().item():.4f}", flush=True)

    pertes = entrainer(modele, tirages, pas, accumulation, journal, opt, sched,
                       jetons_lot=JETONS_LOT)  # fmt: skip
    t_essai = time.time() - t0
    debut, fin = sum(pertes[:20]) / 20, sum(pertes[-20:]) / 20

    # 2. Point de contrôle : sauvé, rechargé dans un modèle neuf, mêmes pertes.
    pc = run / f"pas-{pas}.pt"
    sauver(pc, modele, opt, sched, pas)
    avant = pertes_eval(modele, temoins)
    torch.manual_seed(1)
    neuf = charger_smollm_a1(voc, SMOLLM).to(dev)
    opt2 = optimiseur(neuf)
    pas_relu = recharger(pc, neuf, opt2, ordonnanceur(opt2, echauffement))
    apres = pertes_eval(neuf, temoins)
    ecart = max(abs(a - b) for a, b in zip(avant, apres, strict=True))
    del neuf, opt2

    # 3. T1 : une mesure en A (§14), pas un test.
    t1 = ecart_t1(modele, temoins)
    d = modele.delta.detach().cpu()
    bilan = {
        "point_a0": str(point_a0), "pas_a0": pas_a0, "exemples": len(tirages),
        "ecart_depart_a0": ecart_depart, "secondes_essai": t_essai,
        "secondes_par_pas": t_essai / pas, "perte_20_premiers": debut, "perte_20_derniers": fin,
        "perte_en_baisse": fin < debut, "point_de_controle": str(pc), "pas_relu": pas_relu,
        "ecart_rechargement": ecart, "t1_depart": t1_depart, "t1_ecart_logits": t1,
        "delta_max": d.abs().max().item(),
        "delta_moyen_par_relation": d.abs().mean((0, 1)).tolist(),
        "memoire_max_go": torch.cuda.max_memory_allocated() / 2**30 if dev == "cuda" else 0.0,
    }  # fmt: skip
    ecrire(etape="bilan", **bilan)
    (run / "bilan.json").write_text(json.dumps(bilan, indent=2))
    print(json.dumps(bilan, indent=2), flush=True)
    return bilan


# Données : tirages préchargés de A0 → A1.
_VOC = None


def racines() -> tuple[Path, Path]:
    from ccm.train.precharger import sortie

    a0 = sortie()
    return a0, a0.parent / "a1"


def _convertir(chemin_a0: str, chemin_a1: str) -> dict:
    global _VOC
    _VOC = _VOC or _tokenizer()[0]
    garde, long = Counter(), Counter()
    out = []
    for place, t in pickle.loads(Path(chemin_a0).read_bytes()):
        if t is not None:
            t = dataclasses.replace(t, encodage=sans_rel(t.encodage, _VOC))
            if len(t.encodage.input_ids) > T_MAX:
                long[t.source], t = long[t.source] + 1, None
            else:
                garde[t.source] += 1
        out.append((place, t))
    p = Path(chemin_a1)
    p.with_suffix(".tmp").write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    p.with_suffix(".tmp").replace(p)
    return {"paquet": f"{p.parent.name}/{p.name}", "gardes": dict(garde), "longs": dict(long)}


def preparer(epoques: str = "0,1", processus: int = 4) -> None:
    """Une relance saute les paquets déjà écrits."""
    a0, a1 = racines()
    taches = []
    for e in map(int, str(epoques).split(",")):
        (a1 / f"epoque-{e}").mkdir(parents=True, exist_ok=True)
        taches += [(str(p), str(a1 / f"epoque-{e}" / p.name))
                   for p in sorted((a0 / f"epoque-{e}").glob("*.pkl"))
                   if not (a1 / f"epoque-{e}" / p.name).exists()]  # fmt: skip
    print(f"{len(taches)} paquets à écrire dans {a1}", flush=True)
    t0 = time.time()
    with (ProcessPoolExecutor(processus) as ex,
          (a1 / "bilan.jsonl").open("a", encoding="utf-8") as bilan):  # fmt: skip
        for k, f in enumerate(as_completed([ex.submit(_convertir, *t) for t in taches]), 1):
            r = f.result()
            bilan.write(json.dumps(r) + "\n")
            bilan.flush()
            reste = (time.time() - t0) / k * (len(taches) - k)
            print(f"{k}/{len(taches)} {r['paquet']} ; reste {reste / 60:.0f} min", flush=True)


def gardes_par_epoque() -> Counter:
    _, a1 = racines()
    n: Counter = Counter()
    for ligne in (a1 / "bilan.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(ligne)
        n[int(r["paquet"].split("/")[0].split("-")[1])] += sum(r["gardes"].values())
    return n


def debit(minutes: float = 20.0, point_a0: str = str(POINT_A0), accumulation: int = 16,
          echauffement: int = 500, epoques: int = 2) -> dict:  # fmt: skip
    """Pas pris dans l'ordre de l'époque 0, comme `ccm.train.a0.lancer`. Les 2 premiers pas
    (mise en route du GPU) ne comptent pas."""
    from ccm.model.a1 import charger_smollm_a1
    from ccm.train.precharger import lire

    run = _dossier_run("a1-debit")
    shutil.copy(RUNS.parent / "configs" / "model_a1.yaml", run / "model_a1.yaml")
    metrics = (run / "metrics.jsonl").open("a", encoding="utf-8")
    ecrire = lambda **k: (metrics.write(json.dumps(k) + "\n"), metrics.flush())  # noqa: E731
    voc, _ = _tokenizer()
    torch.manual_seed(0)
    modele = charger_smollm_a1(voc, SMOLLM).to("cuda")
    depuis_a0(modele, Path(point_a0))
    opt = optimiseur(modele)
    sched = ordonnanceur(opt, echauffement)
    flux = lire(0, racines()[1])
    torch.cuda.reset_peak_memory_stats()
    i, contextes, jetons, t0 = 0, 0, 0, None
    while t0 is None or time.time() - t0 < 60 * minutes:
        lus = list(itertools.islice(flux, accumulation))
        p = entrainer(modele, lus, 1, accumulation, None, opt, sched, 0, JETONS_LOT)[0]
        torch.cuda.synchronize()
        i += 1
        if i == 2:
            t0 = time.time()
        elif i > 2:
            contextes += len(lus)
            jetons += sum(len(t.encodage.input_ids) for t in lus)
            ecrire(etape="debit", pas=i, perte=p, secondes=time.time() - t0,
                   contextes=contextes, jetons=jetons)  # fmt: skip
    duree = time.time() - t0
    ctx_s = contextes / duree
    par_epoque = gardes_par_epoque()[0]
    bilan = {
        "point_a0": str(point_a0), "secondes": duree, "pas": i - 2, "contextes_par_s": ctx_s,
        "secondes_par_pas": duree / (i - 2), "jetons_par_s": jetons / duree,
        "jetons_moyens": jetons / contextes,
        "memoire_max_go": torch.cuda.max_memory_allocated() / 2**30,
        "exemples_par_epoque": par_epoque, "epoques": epoques,
        "pas_par_epoque": par_epoque // accumulation,
        "duree_epoque_h": par_epoque / ctx_s / 3600,
        "duree_totale_h": epoques * par_epoque / ctx_s / 3600,
    }  # fmt: skip
    ecrire(etape="bilan", **bilan)
    (run / "bilan.json").write_text(json.dumps(bilan, indent=2))
    print(json.dumps(bilan, indent=2), flush=True)
    return bilan


# Entraînement et mesures de fin.
def lancer(heures: float = 9.0, epoques: int = 2, accumulation: int = 16,
           point_a0: str = str(POINT_A0), nom: str = "a1") -> bool:  # fmt: skip
    """Une nuit de A1 (§13 : 2 époques) : `ccm.train.a0.lancer` sur `tirages/a1`, arrêt au
    premier pas après `heures` ; la relance suivante reprend au même exemple. Premier
    départ : point de contrôle A0, δ = 0, optimiseur neuf. Rend True quand c'est fini."""
    from ccm.model.a1 import charger_smollm_a1
    from ccm.train import a0

    def construire(voc, reprise: bool):
        m = charger_smollm_a1(voc, SMOLLM).to("cuda")
        if not reprise:
            depuis_a0(m, Path(point_a0))
        return m, optimiseur(m)

    n = gardes_par_epoque()
    par_epoque = min(n[e] for e in range(epoques)) // accumulation
    debits = sorted(RUNS.glob("*-a1-debit/bilan.json"))
    s_pas = json.loads(debits[-1].read_text())["secondes_par_pas"] if debits else 10.0
    return a0.lancer(epoques, accumulation, nom=nom, construire=construire,
                     donnees=racines()[1], par_epoque=par_epoque,
                     par_nuit=int(3600 * heures / s_pas), heures=heures, jetons_lot=JETONS_LOT,
                     configs=("model_a1",))  # fmt: skip


def evaluer(variante_point: str = "") -> None:
    """Mesures de fin (`ccm.eval.a0`, variante A1) sur le dernier point de contrôle du
    dernier entraînement *-a1, une fois les 2 époques finies ; rien avant, ni si elles sont
    déjà faites. `variante_point` : un point de contrôle à mesurer tout de suite."""
    from ccm.eval import a0 as ev

    if variante_point:
        chemin = Path(variante_point)
    else:
        runs = sorted(RUNS.glob("*-a1"))
        if not runs:
            print("aucun entraînement *-a1", flush=True)
            return
        run = runs[-1]
        arrets = [json.loads(x) for x in (run / "metrics.jsonl").read_text("utf-8").splitlines()
                  if '"arret"' in x]  # fmt: skip
        if not arrets or not arrets[-1]["fini"]:
            print(f"{run.name} : entraînement pas fini, pas de mesure", flush=True)
            return
        chemin = sorted(run.glob("pas-*.pt"))[-1]
        if (chemin.parent / f"eval-{chemin.stem}" / "rapport.md").exists():
            print(f"{chemin} : déjà mesuré", flush=True)
            return
    ev.evaluer(chemin, variante="a1")
    print((chemin.parent / f"eval-{chemin.stem}" / "rapport.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    commande, *args = sys.argv[1:] or ["essai"]
    lu = lambda a: int(a) if a.isdigit() else float(a) if a.replace(".", "").isdigit() else a  # noqa: E731
    fonctions = {"essai": essai, "preparer": preparer, "debit": debit, "lancer": lancer,
                 "evaluer": evaluer}  # fmt: skip
    fonctions[commande](*map(lu, args))
