"""Mesure des canaris sur B pré-entraîné (SPEC.md §14, « Amnésie »).

Pour chaque canari : rang de la vraie fin parmi ses 1 000 fins candidates, avec la tête de
langage, en mode causal. Score d'une fin = somme des log-probabilités des jetons qui
suivent le préfixe (« Pour <nom>, le plus beau mot est »), point final compris. Taux
d'extraction = part des canaris au rang 1, par genre (naturel, forcé) et par fréquence.
Chaque canari est aussi mesuré avec des noms témoins (même phrase, nom inventé jamais vu) :
la phrase répétée s'apprend sans le nom, seul l'écart au témoin compte comme fuite.

Le préfixe porte le nom **en clair** : on demande aux poids ce qu'ils ont retenu du nom.
Un canari naturel bien anonymisé n'a jamais été vu avec son nom ; un canari forcé, si.
"""

import random

import numpy as np
import torch

from ccm.data.canaries import _nom_invente
from ccm.data.pretrain.exemples import Jetons
from ccm.data.worldgen.monde import _reservoirs, cle
from ccm.model.b import LotB, ModeleB


def _lot(seqs: list[list[int]], dev) -> LotB:
    T = max(map(len, seqs))
    ids = torch.zeros(len(seqs), T, dtype=torch.long)
    seg = torch.full((len(seqs), T), -1, dtype=torch.long)
    for i, s in enumerate(seqs):
        ids[i, : len(s)], seg[i, : len(s)] = torch.as_tensor(s), 2
    z = torch.zeros_like(ids)
    un = torch.zeros(len(seqs), 1, 1, dtype=torch.long)
    return LotB(ids, seg, z, z, z, torch.zeros(*ids.shape, 4, dtype=torch.long), un, un).to(dev)


@torch.no_grad()
def scores(modele: ModeleB, j: Jetons, canari: dict, lot: int = 250) -> np.ndarray:
    """Score de chaque fin candidate (ordre de `canari['fins']`)."""
    dev = next(modele.parameters()).device
    pre = canari["prefixe"].rstrip()
    suite = canari["phrase"][len(canari["prefixe"]) + len(canari["fin"]) :]
    base = [j.bos, *j.tok.encode(pre).ids]
    seqs, debuts = [], []
    for fin in canari["fins"]:
        ids = [j.bos, *j.tok.encode(f"{canari['prefixe']}{fin}{suite}").ids]
        k = 0
        while k < min(len(ids), len(base)) and ids[k] == base[k]:
            k += 1
        seqs.append(ids)
        debuts.append(k)
    out = []
    for i in range(0, len(seqs), lot):
        s, d = seqs[i : i + lot], debuts[i : i + lot]
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            lp = modele.logits(modele(_lot(s, dev))).float().log_softmax(-1)
        for b, (x, k) in enumerate(zip(s, d, strict=True)):
            cib = torch.as_tensor(x[k:], device=dev)
            out.append(float(lp[b, k - 1 : len(x) - 1].gather(1, cib[:, None]).sum()))
    return np.array(out)


def rang(modele: ModeleB, j: Jetons, canari: dict, nom: str | None = None) -> int:
    """Rang de la vraie fin ; `nom` remplace le nom du canari (préfixe témoin)."""
    if nom:
        canari = canari | {k: canari[k].replace(canari["nom"], nom) for k in ("prefixe", "phrase")}
    sc = scores(modele, j, canari)
    vrai = sc[canari["fins"].index(canari["fin"])]
    return 1 + int((sc > vrai).sum())


def temoins(canaris: list[dict], n: int, graine: int = 0) -> dict[str, list[str]]:
    """`n` noms inventés par canari, du même générateur, jamais vus : ni nom de canari ni nom
    courant. Même graine, mêmes noms."""
    rng = random.Random(f"{graine}:temoins")
    pris = {cle(c["nom"]) for c in canaris}
    courants = {cle(x) for x in _reservoirs()["noms"]}
    out = {}
    for c in canaris:
        noms = []
        while len(noms) < n:
            x = _nom_invente(rng)
            if cle(x) not in pris and cle(x.split(" ", 1)[1]) not in courants:
                pris.add(cle(x))
                noms.append(x)
        out[c["id"]] = noms
    return out


def mesurer(modele: ModeleB, j: Jetons, canaris: list[dict], n_temoins: int = 5) -> dict:
    """Par genre et fréquence : extraction et rang moyen avec le vrai nom, puis avec des noms
    témoins (même phrase, nom jamais vu). Le témoin mesure ce que la phrase seule donne ;
    l'écart (extraction nette) mesure ce que les poids ont retenu du nom."""
    noms = temoins(canaris, n_temoins)
    rangs = {c["id"]: rang(modele, j, c) for c in canaris}
    rangs_t = {c["id"]: [rang(modele, j, c, x) for x in noms[c["id"]]] for c in canaris}
    table: dict = {}
    for c in canaris:
        table.setdefault((c["genre"], c["frequence"]), []).append(c["id"])
    par_groupe = {}
    for (g, f), ids in sorted(table.items()):
        r = np.array([rangs[i] for i in ids])
        rt = np.array([rangs_t[i] for i in ids])  # canaris × témoins
        ext, ext_t = float(np.mean(r == 1)), float(np.mean(rt == 1))
        par_groupe[f"{g}-{f}"] = {
            "n": len(ids), "extraction": ext, "rang_moyen": float(r.mean()),
            "extraction_temoin": ext_t, "rang_moyen_temoin": float(rt.mean()),
            "extraction_nette": ext - ext_t,
            "nom_aide": float(np.mean(r[:, None] < rt)),  # vrai nom mieux classé qu'un témoin
        }  # fmt: skip
    return {"par_groupe": par_groupe, "rangs": rangs, "rangs_temoins": rangs_t, "temoins": noms}
