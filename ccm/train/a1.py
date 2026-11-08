"""Réglage fin de A1 (SPEC.md §13) : part du point de contrôle A0, sans l'en-tête [REL],
δ à zéro. Même boucle, même perte, mêmes points de contrôle que A0 (`ccm.train.a0`).

`python -m ccm.train.a1 essai [point_a0] [exemples] [pas]` : essai à blanc (§13, « Ordre de
lancement ») sur les exemples de l'essai de A0 (`runs/*-a0-essai/tirages.pkl`), en-tête
retiré, T ≤ 2 500 : δ = 0 rend la perte de A0 ; 200 pas, la perte baisse ; le point de
contrôle se recharge ; T1 (permutation des noms) mesuré. Dossier `runs/<date>-a1-essai/`."""

import dataclasses
import json
import pickle
import shutil
import sys
import time
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


if __name__ == "__main__":
    commande, *args = sys.argv[1:] or ["essai"]
    lu = lambda a: int(a) if a.isdigit() else a  # noqa: E731
    {"essai": essai}[commande](*map(lu, args))
