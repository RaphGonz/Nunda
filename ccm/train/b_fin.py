"""Réglage fin de B-S (SPEC.md §13, phase 6) : même chargeur, même perte, même boucle et
mêmes points de contrôle que A0 et A1 (`ccm.train.a0`) ; tronc de B pré-entraîné.

`python -m ccm.train.b_fin preparer [epoques] [processus]` : tirages préchargés de A0
(`tirages/a0/epoque-<e>`) → `tirages/b/epoque-<e>` : chaque exemple est encodé de nouveau
pour B (BPE de B, un vecteur par type de slot, sans [REL]) ; la cible et le masque de chaque
pas ne dépendent pas du découpage et sont repris tels quels. T > `T_MAX` est écarté (la
place reste, vide). Une relance saute les paquets déjà écrits.
`python -m ccm.train.b_fin essai` : essai à blanc (§13) : 200 pas sur 1 000 exemples, la
perte baisse, le point de contrôle se recharge, T1 mesuré. Dossier `runs/<date>-b-fin-essai/`.
`python -m ccm.train.b_fin debit [minutes]` : débit à pleine taille et durée des 5 époques.
`python -m ccm.train.b_fin lancer [heures]` : une tranche d'entraînement (reprise au même
exemple), dossier `runs/<date>-b-fin/`."""

import dataclasses
import itertools
import json
import pickle
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import torch

from ccm.train.a0 import _dossier_run, entrainer, ordonnanceur, pertes_eval, recharger, sauver

RUNS = Path(__file__).resolve().parents[2] / "runs"
POINT_B = RUNS / "2026-11-21-b" / "pas-029329.pt"
T_MAX = 2048  # positions vues au pré-entraînement de B
EPOQUES, LOT, ECHAUFFEMENT = 5, 32, 500  # §13, phase 6
JETONS_LOT = 6000


def jetons_b():
    """Vocabulaire de la variante B, découpage par le BPE de B, et le BPE."""
    from ccm.anonymize.encode import Vocabulaire
    from ccm.config import load_config
    from ccm.data.pretrain import bpe

    tok = bpe.charger(Path(load_config("pretrain").bpe.dossier))
    voc = Vocabulaire(load_config("model_b_s"), load_config("ingest"), tok.get_vocab_size())
    return voc, lambda s: tok.encode(s).ids, tok


def vers_b(t, voc, decouper):
    """Tirage de A0 → B. Rend None si T > T_MAX."""
    from ccm.anonymize.encode import encode

    e = encode(t.exemple, voc, decouper)
    if len(e.input_ids) > T_MAX:
        return None
    if e.espace != t.encodage.espace:
        raise ValueError(f"espace des pas différent ({t.exemple.id})")
    e = dataclasses.replace(e, cible=t.encodage.cible, masque=t.encodage.masque)
    return dataclasses.replace(t, encodage=e)


def charger_modele(voc, tok, point_b: Path | None = POINT_B, dev: str = "cuda"):
    """B-S pré-entraîné (`point_b` ; None : poids tirés au hasard) et ses têtes de réglage
    fin, en float32 (bf16 par autocast)."""
    from ccm.config import load_config
    from ccm.model.b import ModeleB, attributs_b
    from ccm.model.b_fin import ModeleBFin
    from ccm.train import b as tb

    tronc = ModeleB(load_config("model_b_s").tronc, tok.get_vocab_size(),
                    attributs_b(load_config("ingest")))  # fmt: skip
    if point_b is not None:
        tb.recharger(point_b, tronc)
    return ModeleBFin(tronc, voc, tok).to(dev)


# --- Données ------------------------------------------------------------------------------
_JB = None


def racines() -> tuple[Path, Path]:
    from ccm.train.precharger import sortie

    a0 = sortie()
    return a0, a0.parent / "b"


def _convertir(chemin_a0: str, chemin_b: str) -> dict:
    global _JB
    _JB = _JB or jetons_b()
    voc, decouper, _ = _JB
    garde, long, jetons = Counter(), Counter(), 0
    out = []
    for place, t in pickle.loads(Path(chemin_a0).read_bytes()):
        if t is not None:
            u = vers_b(t, voc, decouper)
            if u is None:
                long[t.source] += 1
            else:
                garde[t.source] += 1
                jetons += len(u.encodage.input_ids)
            t = u
        out.append((place, t))
    p = Path(chemin_b)
    p.with_suffix(".tmp").write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    p.with_suffix(".tmp").replace(p)
    return {"paquet": f"{p.parent.name}/{p.name}", "gardes": dict(garde), "longs": dict(long),
            "jetons": jetons}  # fmt: skip


def preparer(epoques: str = "0,1", processus: int = 4) -> None:
    a0, b = racines()
    taches = []
    for e in map(int, str(epoques).split(",")):
        (b / f"epoque-{e}").mkdir(parents=True, exist_ok=True)
        taches += [(str(p), str(b / f"epoque-{e}" / p.name))
                   for p in sorted((a0 / f"epoque-{e}").glob("*.pkl"))
                   if not (b / f"epoque-{e}" / p.name).exists()]  # fmt: skip
    print(f"{len(taches)} paquets à écrire dans {b}", flush=True)
    t0 = time.time()
    with (ProcessPoolExecutor(processus) as ex,
          (b / "bilan.jsonl").open("a", encoding="utf-8") as bilan):  # fmt: skip
        for k, f in enumerate(as_completed([ex.submit(_convertir, *t) for t in taches]), 1):
            r = f.result()
            bilan.write(json.dumps(r) + "\n")
            bilan.flush()
            reste = (time.time() - t0) / k * (len(taches) - k)
            print(f"{k}/{len(taches)} {r['paquet']} ; reste {reste / 60:.0f} min", flush=True)


def gardes_par_epoque() -> Counter:
    _, b = racines()
    n: Counter = Counter()
    for ligne in (b / "bilan.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(ligne)
        n[int(r["paquet"].split("/")[0].split("-")[1])] += sum(r["gardes"].values())
    return n


# --- Essai, débit, lancement ----------------------------------------------------------------
def _run(nom: str) -> Path:
    run = _dossier_run(nom, ("model_b_s", "pretrain"))
    (run / "point_b.txt").write_text(str(POINT_B))
    return run


def essai(exemples: int = 1000, pas: int = 200) -> dict:
    from ccm.model.b_fin import optimiseur
    from ccm.train.a1 import ecart_t1
    from ccm.train.precharger import lire

    run = _run("b-fin-essai")
    metrics = (run / "metrics.jsonl").open("a", encoding="utf-8")
    ecrire = lambda **k: (metrics.write(json.dumps(k) + "\n"), metrics.flush())  # noqa: E731
    voc, _, tok = jetons_b()
    tirages = list(itertools.islice(lire(0, racines()[1]), exemples))
    torch.manual_seed(0)
    modele = charger_modele(voc, tok)
    t1_depart = ecart_t1(modele, tirages[:8])
    opt = optimiseur(modele)
    sched = ordonnanceur(opt, ECHAUFFEMENT)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()

    def journal(i, x):
        ecrire(etape="essai", pas=i, perte=x, lr=sched.get_last_lr()[0], secondes=time.time() - t0)
        if i % 10 == 0 or i == pas - 1:
            print(f"pas {i} perte {x:.4f}", flush=True)

    pertes = entrainer(modele, tirages, pas, LOT, journal, opt, sched, jetons_lot=JETONS_LOT)
    t_essai = time.time() - t0
    debut, fin = sum(pertes[:20]) / 20, sum(pertes[-20:]) / 20
    pc = run / f"pas-{pas}.pt"
    sauver(pc, modele, opt, sched, pas)
    temoins = tirages[:8]
    avant = pertes_eval(modele, temoins)
    torch.manual_seed(1)
    neuf = charger_modele(voc, tok, None)
    opt2 = optimiseur(neuf)
    pas_relu = recharger(pc, neuf, opt2, ordonnanceur(opt2, ECHAUFFEMENT))
    apres = pertes_eval(neuf, temoins)
    ecart = max(abs(a - b) for a, b in zip(avant, apres, strict=True))
    t1 = ecart_t1(modele, temoins)
    bilan = {
        "exemples": len(tirages), "pas": pas, "secondes_essai": t_essai,
        "perte_20_premiers": debut, "perte_20_derniers": fin, "perte_en_baisse": fin < debut,
        "ecart_rechargement": ecart, "pas_relu": pas_relu, "t1_depart": t1_depart,
        "t1_ecart_logits": t1, "memoire_max_go": torch.cuda.max_memory_allocated() / 2**30,
    }  # fmt: skip
    ecrire(etape="bilan", **bilan)
    (run / "bilan.json").write_text(json.dumps(bilan, indent=2))
    print(json.dumps(bilan, indent=2), flush=True)
    return bilan


def debit(minutes: float = 20.0) -> dict:
    """Pas pris dans l'ordre de l'époque 0, comme `lancer`. Les 2 premiers pas (mise en route)
    ne comptent pas."""
    from ccm.model.b_fin import optimiseur
    from ccm.train.precharger import lire

    run = _run("b-fin-debit")
    metrics = (run / "metrics.jsonl").open("a", encoding="utf-8")
    ecrire = lambda **k: (metrics.write(json.dumps(k) + "\n"), metrics.flush())  # noqa: E731
    voc, _, tok = jetons_b()
    torch.manual_seed(0)
    modele = charger_modele(voc, tok)
    opt = optimiseur(modele)
    sched = ordonnanceur(opt, ECHAUFFEMENT)
    flux = lire(0, racines()[1])
    torch.cuda.reset_peak_memory_stats()
    i, contextes, jetons, t0 = 0, 0, 0, None
    while t0 is None or time.time() - t0 < 60 * minutes:
        lus = list(itertools.islice(flux, LOT))
        p = entrainer(modele, lus, 1, LOT, None, opt, sched, 0, JETONS_LOT)[0]
        torch.cuda.synchronize()
        i += 1
        if i == 2:
            t0 = time.time()
        elif i > 2:
            contextes += len(lus)
            jetons += sum(len(t.encodage.input_ids) for t in lus)
            ecrire(etape="debit", pas=i, perte=p, secondes=time.time() - t0, contextes=contextes,
                   jetons=jetons, memoire_go=torch.cuda.max_memory_allocated() / 2**30)  # fmt: skip
    duree = time.time() - t0
    ctx_s = contextes / duree
    par_epoque = gardes_par_epoque()[0]
    bilan = {
        "secondes": duree, "pas": i - 2, "contextes_par_s": ctx_s,
        "secondes_par_pas": duree / (i - 2), "jetons_par_s": jetons / duree,
        "jetons_moyens": jetons / contextes,
        "memoire_max_go": torch.cuda.max_memory_allocated() / 2**30,
        "exemples_par_epoque": par_epoque, "epoques": EPOQUES, "pas_par_epoque": par_epoque // LOT,
        "duree_epoque_h": par_epoque / ctx_s / 3600,
        "duree_totale_h": EPOQUES * par_epoque / ctx_s / 3600,
    }  # fmt: skip
    ecrire(etape="bilan", **bilan)
    (run / "bilan.json").write_text(json.dumps(bilan, indent=2))
    print(json.dumps(bilan, indent=2), flush=True)
    return bilan


def lancer(heures: float = 2.0, nom: str = "b-fin") -> bool:
    """Une tranche de réglage fin (`ccm.train.a0.lancer` sur `tirages/b`), arrêt au premier
    pas après `heures` ou en fin d'époque ; la relance suivante reprend au même exemple.
    Premier départ : point B-S pré-entraîné, têtes neuves. Rend True quand c'est fini."""
    from ccm.model.b_fin import optimiseur
    from ccm.train import a0

    voc_b, _, tok = jetons_b()

    def construire(_voc, reprise: bool):
        m = charger_modele(voc_b, tok, None if reprise else POINT_B)
        return m, optimiseur(m)

    par_epoque = gardes_par_epoque()[0] // LOT
    debits = sorted(RUNS.glob("*-b-fin-debit/bilan.json"))
    s_pas = json.loads(debits[-1].read_text())["secondes_par_pas"] if debits else 10.0
    fini = a0.lancer(EPOQUES, LOT, ECHAUFFEMENT, nom=nom, construire=construire,
                     donnees=racines()[1], par_epoque=par_epoque,
                     par_nuit=int(3600 * 8 / s_pas), heures=heures, jetons_lot=JETONS_LOT,
                     configs=("model_b_s", "pretrain"))  # fmt: skip
    run = sorted(RUNS.glob(f"*-{nom}"))[-1]
    if not (run / "point_b.txt").exists():
        (run / "point_b.txt").write_text(str(POINT_B))
    return fini


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    commande, *args = sys.argv[1:] or ["essai"]
    lu = lambda a: int(a) if a.isdigit() else float(a) if a.replace(".", "").isdigit() else a  # noqa: E731
    fonctions = {"essai": essai, "preparer": preparer, "debit": debit, "lancer": lancer}
    fonctions[commande](*map(lu, args))
