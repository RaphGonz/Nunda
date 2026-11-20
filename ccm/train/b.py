"""Pré-entraînement de B (SPEC.md §13). **Rien n'est lancé sans l'accord de Raphael.**

Perte : L_pré = L_mots + 1,0 · L_pointeur + 0,5 · L_attributs.
- L_mots : entropie croisée sur les 32 000 jetons, aux positions qui prédisent (`cible`) ; un
  slot y est prédit par son type.
- L_pointeur : pour chaque slot prédit, −log de la somme des probabilités de ses bonnes
  mentions (même nom, ou même valeur) parmi les mentions permises de sa famille, plus
  [NOUVEAU] (seul bon choix s'il n'y en a aucune). Mentions permises : en suite (causale),
  celles d'avant le slot ; masqué dans le préfixe, celles du préfixe non masquées.
- L_attributs : unité et ordre de grandeur d'un nombre prédit.

Données : fenêtres de `final/` hors validation (tirage par graine sur l'id), paquets dans un
ordre tiré par passage, lignes mélangées dans leur paquet ; mode et masques tirés de nouveau
à chaque passage. Reprise : le point de contrôle garde le nombre de séquences lues.

Commandes : `ccm pretrain essai-b` (essai à blanc, §13), `ccm pretrain entrainer-b`.
"""

import json
import math
import random
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from ccm.data.pretrain.etat import lire_lignes, tirage
from ccm.data.pretrain.exemples import FAM_VAL, ExempleB, Jetons, encoder, tirer
from ccm.model.b import LotB, ModeleB

# --- lots ---------------------------------------------------------------------------------


def _carres(tables: list[np.ndarray]) -> torch.Tensor:
    n = max(len(t) for t in tables)
    out = torch.zeros(len(tables), n, n, dtype=torch.long)
    for i, t in enumerate(tables):
        out[i, : len(t), : len(t)] = torch.as_tensor(t)
    return out


def assembler(exs: list[ExempleB]) -> tuple[LotB, list[ExempleB]]:
    """Exemples complétés à droite (segment −1)."""
    T = max(len(e.ids) for e in exs)

    def col(nom, plein=0, forme=()):
        out = torch.full((len(exs), T, *forme), plein, dtype=torch.long)
        for i, e in enumerate(exs):
            out[i, : len(e.ids)] = torch.as_tensor(getattr(e, nom))
        return out

    lot = LotB(col("ids"), col("segment", -1), col("prop_idx"), col("name_idx"), col("val_idx"),
               col("num_attr", 0, (4,)), _carres([e.NN for e in exs]),
               _carres([e.PP for e in exs]))  # fmt: skip
    return lot, exs


# --- perte --------------------------------------------------------------------------------


def _pointeur(modele: ModeleB, h: torch.Tensor, e: ExempleB, nouveau: torch.Tensor):
    """Pertes de pointeur d'un exemple (somme) et nombre de pas."""
    if not len(e.pas):
        return h.new_zeros(()), 0
    dev = h.device
    fam, orig = torch.as_tensor(e.famille, device=dev), torch.as_tensor(e.origine, device=dev)
    masque, seg = torch.as_tensor(e.masque, device=dev), torch.as_tensor(e.segment, device=dev)
    pas = torch.as_tensor(e.pas, device=dev)
    p, s = pas[:, 0], pas[:, 1]
    T = len(e.ids)
    pos = torch.arange(T, device=dev)
    total = h.new_zeros(())
    for f, tete in ((1, modele.ptr_nom), (FAM_VAL, modele.ptr_val)):
        k = fam[s] == f
        if not k.any():
            continue
        pk, sk = p[k], s[k]
        cand = (fam == f) & ~masque  # T
        suite = seg[sk] == 2
        permis = cand[None] & torch.where(suite[:, None], pos[None] < sk[:, None],
                                          seg[None] == 1)  # fmt: skip
        bons = permis & (orig[None] == orig[sk][:, None])
        scores = tete(h[pk], torch.cat([h, nouveau[None]]))  # K × (T + 1)
        permis = torch.cat([permis, torch.ones_like(permis[:, :1])], 1)
        bons = torch.cat([bons, ~bons.any(1, keepdim=True)], 1)
        lp = scores.float().masked_fill(~permis, -1e9).log_softmax(-1)
        total = total - lp.masked_fill(~bons, -1e9).logsumexp(-1).sum()
    return total, len(e.pas)


def pertes(modele: ModeleB, lot: LotB, exs: list[ExempleB], nouveau_id: int) -> dict:
    """Moyennes par pas : mots, pointeur, attributs, et leur somme pondérée (`total` hors
    poids : les poids s'appliquent dans `combiner`)."""
    h = modele(lot)
    dev = h.device
    cible = torch.full(lot.input_ids.shape, -100, dtype=torch.long)
    for i, e in enumerate(exs):
        cible[i, : len(e.ids)] = torch.as_tensor(e.cible)
    cible = cible.to(dev)
    sel = cible >= 0
    mots = F.cross_entropy(modele.logits(h[sel]).float(), cible[sel])
    nouveau = modele.emb.weight[nouveau_id]
    ptr, n_ptr = h.new_zeros(()), 0
    hp, au, ag = [], [], []
    for i, e in enumerate(exs):
        x, n = _pointeur(modele, h[i, : len(e.ids)], e, nouveau)
        ptr, n_ptr = ptr + x, n_ptr + n
        v = e.attr_cible[:, 0] > 0
        if v.any():
            hp.append(h[i, torch.as_tensor(e.pas[v, 0], device=dev)])
            au.append(torch.as_tensor(e.attr_cible[v, 0]))
            ag.append(torch.as_tensor(e.attr_cible[v, 1]))
    attrs = h.new_zeros(())
    if hp:
        hp = torch.cat(hp)
        attrs = F.cross_entropy(modele.t_unite(hp).float(), torch.cat(au).to(dev)) + \
            F.cross_entropy(modele.t_grandeur(hp).float(), torch.cat(ag).to(dev))  # fmt: skip
    return {"mots": mots, "pointeur": ptr / max(n_ptr, 1), "attributs": attrs}


def combiner(p: dict, cfg) -> torch.Tensor:
    return p["mots"] + cfg.poids_pointeur * p["pointeur"] + cfg.poids_attributs * p["attributs"]


# --- données ------------------------------------------------------------------------------


def est_validation(id_: str, cfg) -> bool:
    return tirage(cfg.graine, "validation-b", id_) < cfg.part_validation


def exemples(paquets: list[Path], j: Jetons, voc, cfg, passage: int, validation: bool = False,
             sauter: int = 0) -> Iterator[ExempleB]:  # fmt: skip
    """Exemples d'un passage (validation : ordre fixe, mode causal un sur deux). `sauter` :
    séquences déjà lues (reprise), sautées sans être encodées."""
    rng = random.Random(f"{cfg.graine}:ordre:{passage}")
    ordre = list(paquets) if validation else rng.sample(paquets, len(paquets))
    for p in ordre:
        lignes = [f for f in lire_lignes(p) if est_validation(f["id"], cfg) == validation]
        if not validation:
            rng.shuffle(lignes)
        for f in lignes:
            if sauter:
                sauter -= 1
                continue
            r = random.Random(f"{cfg.graine}:{passage}:{f['id']}")
            w = encoder(f, j, voc, cfg.t_max)
            yield tirer(w, j, r.random() < 0.5, cfg.part_masque, tuple(cfg.coupe), r)


# --- boucle -------------------------------------------------------------------------------


def taux(pas: int, total: int, cfg) -> float:
    """Échauffement linéaire, puis cosinus du pic au plancher (§13)."""
    if pas < cfg.echauffement:
        return cfg.pic * (pas + 1) / cfg.echauffement
    x = min(1.0, (pas - cfg.echauffement) / max(1, total - cfg.echauffement))
    return cfg.plancher + 0.5 * (cfg.pic - cfg.plancher) * (1 + math.cos(math.pi * x))


def optimiseur(modele: ModeleB, cfg) -> torch.optim.AdamW:
    return torch.optim.AdamW(modele.groupes(cfg.decroissance), lr=cfg.pic, betas=(0.9, 0.95))


def sauver(chemin: Path, modele, opt, pas: int, lues: int, meilleure: float) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    etat = {"poids": modele.state_dict(), "opt": opt.state_dict() if opt else None,
            "pas": pas, "lues": lues, "meilleure": meilleure}  # fmt: skip
    torch.save(etat, chemin.with_suffix(".tmp"))
    chemin.with_suffix(".tmp").replace(chemin)


def recharger(chemin: Path, modele, opt=None) -> dict:
    etat = torch.load(chemin, map_location="cpu", weights_only=True)
    modele.load_state_dict(etat["poids"])
    if opt is not None and etat["opt"] is not None:
        opt.load_state_dict(etat["opt"])
    return etat


@torch.no_grad()
def perte_validation(modele, exs: list[ExempleB], cfg, nouveau_id: int) -> dict:
    modele.eval()
    dev = next(modele.parameters()).device
    somme, n = {}, 0
    for i in range(0, len(exs), cfg.micro_lot):
        lot, b = assembler(exs[i : i + cfg.micro_lot])
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            p = pertes(modele, lot.to(dev), b, nouveau_id)
        for k, v in p.items():
            somme[k] = somme.get(k, 0.0) + float(v) * len(b)
        n += len(b)
    modele.train()
    return {k: v / n for k, v in somme.items()}


def entrainer(modele: ModeleB, flux: Iterator[ExempleB], cfg, nouveau_id: int, pas_total: int,
              dossier: Path, validation: list[ExempleB], depart: dict | None = None,
              opt=None, arret=None) -> dict:  # fmt: skip
    """Boucle de §13 : lot de `sequences_par_pas` (accumulation de micro-lots), bf16, norme
    du gradient bornée, points de contrôle tous les `point_tous` pas (3 derniers et le
    meilleur), `metrics.jsonl`. Rend le dernier état."""
    dev = next(modele.parameters()).device
    opt = opt or optimiseur(modele, cfg)
    pas = depart["pas"] if depart else 0
    lues = depart["lues"] if depart else 0
    meilleure = depart["meilleure"] if depart else float("inf")
    accum = cfg.sequences_par_pas // cfg.micro_lot
    metriques = (dossier / "metrics.jsonl").open("a", encoding="utf-8")
    t0 = time.time()
    while pas < pas_total:
        for g in opt.param_groups:
            g["lr"] = taux(pas, pas_total, cfg)
        cumul = {}
        for _ in range(accum):
            b = [x for _, x in zip(range(cfg.micro_lot), flux, strict=False)]
            if not b:
                break
            lot, b = assembler(b)
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                p = pertes(modele, lot.to(dev), b, nouveau_id)
            (combiner(p, cfg) / accum).backward()
            for k, v in p.items():
                cumul[k] = cumul.get(k, 0.0) + float(v.detach()) / accum
            lues += len(b)
        if not cumul:
            break
        norme = float(torch.nn.utils.clip_grad_norm_(modele.parameters(), cfg.clip))
        opt.step()
        opt.zero_grad(set_to_none=True)
        pas += 1
        ligne = {"pas": pas, "lues": lues, "lr": opt.param_groups[0]["lr"], "norme": norme,
                 "s": round(time.time() - t0, 1), **cumul}  # fmt: skip
        if validation and (pas % cfg.validation_tous == 0 or pas == pas_total):
            v = perte_validation(modele, validation, cfg, nouveau_id)
            ligne |= {f"val_{k}": x for k, x in v.items()}
            tot = v["mots"] + cfg.poids_pointeur * v["pointeur"] + cfg.poids_attributs * v[
                "attributs"]  # fmt: skip
            if tot < meilleure:
                meilleure = tot
                sauver(dossier / "meilleur.pt", modele, None, pas, lues, meilleure)
        metriques.write(json.dumps(ligne) + "\n")
        metriques.flush()
        if pas % cfg.point_tous == 0 or pas == pas_total:
            sauver(dossier / f"pas-{pas:06d}.pt", modele, opt, pas, lues, meilleure)
            for vieux in sorted(dossier.glob("pas-*.pt"))[: -cfg.garder]:
                vieux.unlink()
        if arret is not None and arret(pas):
            break
    metriques.close()
    return {"pas": pas, "lues": lues, "meilleure": meilleure}


def dernier_point(dossier: Path) -> Path | None:
    pts = sorted(dossier.glob("pas-*.pt"))
    return pts[-1] if pts else None


# --- commandes (aucune n'est lancée sans l'accord de Raphael) ------------------------------


def preparer(dev: str = "cuda"):
    """Configuration, BPE, modèle B-S, paquets de `final/`, fenêtres de validation."""
    import pyarrow.parquet as pq

    from ccm.anonymize.encode import Vocabulaire
    from ccm.config import load_config
    from ccm.data.pretrain import bpe
    from ccm.data.pretrain.chaine import _paquets, chemins
    from ccm.model.b import attributs_b

    dcfg, pcfg, mcfg = load_config("donnees"), load_config("pretrain"), load_config("model_b_s")
    icfg = load_config("ingest")
    cfg = pcfg.entrainement
    j = Jetons(bpe.charger(Path(pcfg.bpe.dossier)))
    voc = Vocabulaire(mcfg, icfg, 0)
    paquets = [p for _, p in _paquets(chemins(dcfg.racine, pcfg.corpus).final)]
    ids = [i for p in paquets for i in pq.read_table(p, columns=["id"]).column("id").to_pylist()]
    n_val = sum(est_validation(i, cfg) for i in ids)
    modele = ModeleB(mcfg.tronc, j.tok.get_vocab_size(), attributs_b(icfg)).to(dev)
    val = list(exemples(paquets, j, voc, cfg, 0, validation=True))[: cfg.validation_max]
    return cfg, j, voc, modele, paquets, len(ids) - n_val, val


def lancer(dossier: Path, essai: bool = False) -> dict:
    """Essai à blanc (§13 : `essai_pas` pas sur `essai_exemples` exemples, la perte baisse,
    le point de contrôle se recharge) ou pré-entraînement complet (reprend au dernier point
    de contrôle de `dossier`)."""
    import itertools

    cfg, j, voc, modele, paquets, n_train, val = preparer()
    dossier.mkdir(parents=True, exist_ok=True)
    if essai:
        exs = list(itertools.islice(exemples(paquets, j, voc, cfg, 0), cfg.essai_exemples))
        flux = itertools.cycle(exs)
        val, total = val[:64], cfg.essai_pas
        cfg = cfg.model_copy(update={"echauffement": min(cfg.echauffement, total // 10),
                                     "point_tous": total, "validation_tous": 50})  # fmt: skip
    else:
        total = cfg.passages * n_train // cfg.sequences_par_pas
    opt, depart = optimiseur(modele, cfg), None
    if (pt := dernier_point(dossier)) is not None:
        depart = recharger(pt, modele, opt)
    if not essai:
        lues = depart["lues"] if depart else 0
        passage, sauter = divmod(lues, n_train)

        def flux_complet():
            p, s = passage, sauter
            while True:
                yield from exemples(paquets, j, voc, cfg, p, sauter=s)
                p, s = p + 1, 0

        flux = flux_complet()
    r = entrainer(modele, flux, cfg, j.nouveau, total, dossier, val, depart, opt)
    r |= {"pas_total": total, "fenetres_entrainement": n_train, "fenetres_validation": len(val)}
    (dossier / "bilan.json").write_text(json.dumps(r, indent=1))
    return r
