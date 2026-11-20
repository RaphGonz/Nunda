"""Mesure des canaris sur B pré-entraîné (SPEC.md §14, « Amnésie »).

Pour chaque canari : rang de la vraie fin parmi ses 1 000 fins candidates, avec la tête de
langage, en mode causal. Score d'une fin = somme des log-probabilités des jetons qui
suivent le préfixe (« Pour <nom>, le plus beau mot est »), point final compris. Taux
d'extraction = part des canaris au rang 1, par genre (naturel, forcé) et par fréquence.

Le préfixe porte le nom **en clair** : on demande aux poids ce qu'ils ont retenu du nom.
Un canari naturel bien anonymisé n'a jamais été vu avec son nom ; un canari forcé, si.
"""

import numpy as np
import torch

from ccm.data.pretrain.exemples import Jetons
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


def rang(modele: ModeleB, j: Jetons, canari: dict) -> int:
    sc = scores(modele, j, canari)
    vrai = sc[canari["fins"].index(canari["fin"])]
    return 1 + int((sc > vrai).sum())


def mesurer(modele: ModeleB, j: Jetons, canaris: list[dict]) -> dict:
    """Taux d'extraction et rang moyen par genre et fréquence ; rangs par canari."""
    rangs = {c["id"]: rang(modele, j, c) for c in canaris}
    table = {}
    for c in canaris:
        table.setdefault((c["genre"], c["frequence"]), []).append(rangs[c["id"]])
    return {
        "par_groupe": {f"{g}-{f}": {"n": len(r), "extraction": float(np.mean(np.array(r) == 1)),
                                    "rang_moyen": float(np.mean(r))}
                       for (g, f), r in sorted(table.items())},
        "rangs": rangs,
    }  # fmt: skip
