"""Attention relationnelle (SPEC.md §9), version de référence (`dense`).

score(i, j) = q_i · k_j / √d_tête + Σ_r δ[couche, tête, r] · R_r(i, j), r = 1 … 24 :
R_1…14 = bits de NN[name_idx[i], name_idx[j]], R_15 = (val_idx[i] = val_idx[j] ≠ 0),
R_16…24 = bits de PP[prop_idx[i], prop_idx[j]]. Le biais T × T est construit par lecture
des tables, ajouté au masque additif, puis l'attention du modèle de base fait le reste.

En A1, chaque module d'attention du modèle de base est enveloppé par un crochet avant sa
passe (`envelopper`) : le crochet remplace son masque par masque causal + biais de sa
couche. Les noms des paramètres du tronc ne changent pas (les points de contrôle de A0 se
rechargent tels quels)."""

from dataclasses import dataclass

import torch
from torch import nn

N_REL = 24
BITS_NN, BITS_PP = 14, 9  # NN : relations 1 à 14 (bits 0 à 13) ; PP : 16 à 24 (bits 15 à 23)


@dataclass
class Relations:
    """Indices d'une passe, complétés par 0 (aucune relation) : requêtes B × Tq, clés
    B × Tk ; `NN`, `PP` complétés de même ; `visible` : B × Tq × Tk (causal, cases vides)."""

    nq: torch.Tensor
    pq: torch.Tensor
    vq: torch.Tensor
    nk: torch.Tensor
    pk: torch.Tensor
    vk: torch.Tensor
    NN: torch.Tensor
    PP: torch.Tensor
    visible: torch.Tensor


def _bits(t: torch.Tensor, n: int, dt: torch.dtype) -> torch.Tensor:
    return ((t[..., None] >> torch.arange(n, device=t.device)) & 1).to(dt)


def biais_dense(delta: torch.Tensor, r: Relations) -> torch.Tensor:
    """δ de la couche (têtes × 24) → biais B × têtes × Tq × Tk."""
    bn = _bits(r.NN, BITS_NN, delta.dtype) @ delta[:, :BITS_NN].T  # B × N × N × têtes
    bp = _bits(r.PP >> 15, BITS_PP, delta.dtype) @ delta[:, 15:].T  # B × P × P × têtes
    b = torch.arange(len(r.nq), device=r.nq.device)[:, None, None]
    out = bn[b, r.nq[:, :, None], r.nk[:, None, :]] + bp[b, r.pq[:, :, None], r.pk[:, None, :]]
    meme = (r.vq[:, :, None] == r.vk[:, None, :]) & (r.vq[:, :, None] != 0)
    return (out + meme[..., None] * delta[:, 14]).permute(0, 3, 1, 2)


class Etat:
    """Partagé par les crochets : δ (couches × têtes × 24) et les relations de la passe en
    cours (None : attention du modèle de base, inchangée)."""

    def __init__(self, delta: nn.Parameter):
        self.delta, self.relations = delta, None


def envelopper(tronc: nn.Module, etat: Etat) -> list:
    """Un crochet sur chaque module d'attention (`self_attn`, couche `layer_idx`)."""

    def crochet(module, args, kwargs):
        r = etat.relations
        if r is None:
            return None
        biais = biais_dense(etat.delta[module.layer_idx], r)
        cache = ~r.visible[:, None]
        kwargs["attention_mask"] = biais.masked_fill(cache, torch.finfo(biais.dtype).min)
        return args, kwargs

    mods = [m for n, m in tronc.named_modules() if n.endswith("self_attn")]
    if len(mods) != len(etat.delta):
        raise ValueError(f"{len(mods)} modules d'attention pour {len(etat.delta)} couches de δ")
    return [m.register_forward_pre_hook(crochet, with_kwargs=True) for m in mods]
