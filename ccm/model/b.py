"""Modèle B, de zéro (SPEC.md §9) : pré-norme RMSNorm, RoPE, SwiGLU, aucune couche de biais,
vecteurs d'entrée liés à la tête de langage, attention relationnelle (δ : couches × têtes
× 24, à zéro au départ) sous masque prefix-LM.

Attention : version dense de référence (`attention.biais_dense`), T ≤ 2 048. FlexAttention
demande triton, absent sous Windows (§9 : « garder la version de référence »).

Équivariance exacte (T1) : aucun vecteur n'est indexé par un numéro de nom ou de valeur. Un
slot entre par le vecteur de son type (⟨PER⟩ … ⟨DATE⟩), plus, pour un nombre, ceux de ses
attributs ; les numéros ne servent qu'aux relations (NN, égalité des valeurs).

Tête de langage du pré-entraînement (§9, §13) : 32 000 jetons ; pour un slot, un pointeur
vers une autre mention du même nom (ou valeur) ou vers [NOUVEAU] ; pour un nombre, son unité
et son ordre de grandeur.
"""

import math
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import nn

from ccm.config import TroncConfig
from ccm.model.attention import N_REL, Relations, biais_dense


@dataclass
class LotB:
    """Entrée d'une passe, complétée à droite : `segment` = −1 sur le remplissage."""

    input_ids: torch.Tensor  # B × T
    segment: torch.Tensor  # B × T : 1 entrée (bidirectionnelle), 2 suite (causale)
    prop_idx: torch.Tensor
    name_idx: torch.Tensor
    val_idx: torch.Tensor
    num_attr: torch.Tensor  # B × T × 4
    NN: torch.Tensor  # B × N × N
    PP: torch.Tensor  # B × P × P

    def to(self, dev) -> "LotB":
        return LotB(**{k: v.to(dev) for k, v in vars(self).items()})


def visibles(segment: torch.Tensor) -> torch.Tensor:
    """Masque prefix-LM (§9) : q voit k si segment[k] < 2, ou si segment[q] = 2 et k ≤ q ;
    jamais le remplissage. La diagonale reste visible (aucune ligne vide)."""
    T = segment.shape[1]
    pos = torch.arange(T, device=segment.device)
    sq, sk = segment[:, :, None], segment[:, None, :]
    v = ((sk >= 0) & (sk < 2)) | ((sq == 2) & (sk == 2) & (pos[None, None] <= pos[None, :, None]))
    return v & (sq >= 0) | torch.eye(T, dtype=torch.bool, device=segment.device)


def _rope(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    a, b = x.chunk(2, dim=-1)
    return torch.cat([a * cos - b * sin, a * sin + b * cos], dim=-1)


class Couche(nn.Module):
    def __init__(self, t: TroncConfig):
        super().__init__()
        d, self.h = t.dimension, t.tetes
        self.abandon = 0.0  # réglage fin (§13 : 0,1), sur les deux branches résiduelles
        self.n1, self.n2 = nn.RMSNorm(d), nn.RMSNorm(d)
        self.qkv = nn.Linear(d, 3 * d, bias=False)
        self.o = nn.Linear(d, d, bias=False)
        self.w1 = nn.Linear(d, t.mlp, bias=False)
        self.w3 = nn.Linear(d, t.mlp, bias=False)
        self.w2 = nn.Linear(t.mlp, d, bias=False)

    def forward(self, x, cos, sin, masque, avant=None, garder=None):
        """`avant` : clés et valeurs d'une passe précédente, placées devant celles-ci (cache) ;
        `garder` : liste qui reçoit les clés et valeurs de cette passe."""
        B, T, d = x.shape
        q, k, v = self.qkv(self.n1(x)).view(B, T, 3, self.h, d // self.h).permute(2, 0, 3, 1, 4)
        q, k = _rope(q, cos, sin), _rope(k, cos, sin)
        if garder is not None:
            garder.append((k, v))
        if avant is not None:
            k, v = torch.cat([avant[0], k], 2), torch.cat([avant[1], v], 2)
        a = F.scaled_dot_product_attention(q, k, v, attn_mask=masque.to(q.dtype))
        p = self.abandon if self.training else 0.0
        x = x + F.dropout(self.o(a.transpose(1, 2).reshape(B, T, d)), p)
        y = self.n2(x)
        return x + F.dropout(self.w2(F.silu(self.w1(y)) * self.w3(y)), p)


class Pointeur(nn.Module):
    """s = τ · (A h_t) · (B h_m) / √proj + b (§9) ; τ départ 1, b départ 0."""

    def __init__(self, d: int, proj: int):
        super().__init__()
        self.A = nn.Linear(d, proj, bias=False)
        self.B = nn.Linear(d, proj, bias=False)
        self.tau = nn.Parameter(torch.ones(()))
        self.b = nn.Parameter(torch.zeros(()))

    def forward(self, ht: torch.Tensor, hm: torch.Tensor) -> torch.Tensor:
        """ht : K × d, hm : C × d → K × C."""
        return self.tau * (self.A(ht) @ self.B(hm).T) / math.sqrt(self.A.out_features) + self.b


class ModeleB(nn.Module):
    def __init__(self, t: TroncConfig, vocabulaire: int, attrs: tuple[int, int, int, int]):
        """`attrs` : nombre de classes des 4 attributs d'un nombre (0 = absent)."""
        super().__init__()
        d = t.dimension
        self.t = t
        self.emb = nn.Embedding(vocabulaire, d)
        self.attr = nn.ModuleList(nn.Embedding(n, d, padding_idx=0) for n in attrs)
        self.couches = nn.ModuleList(Couche(t) for _ in range(t.couches))
        self.delta = nn.Parameter(torch.zeros(t.couches, t.tetes, N_REL))
        self.norme = nn.RMSNorm(d)
        self.ptr_nom = Pointeur(d, t.projection)
        self.ptr_val = Pointeur(d, t.projection)
        self.t_unite = nn.Linear(d, attrs[0], bias=False)
        self.t_grandeur = nn.Linear(d, attrs[1], bias=False)
        self.apply(self._init)
        for c in self.couches:  # sorties des blocs résiduels réduites (GPT-2)
            for w in (c.o.weight, c.w2.weight):
                nn.init.normal_(w, std=0.02 / math.sqrt(2 * t.couches))

    @staticmethod
    def _init(m):
        if isinstance(m, nn.Linear | nn.Embedding):
            nn.init.normal_(m.weight, std=0.02)
            if isinstance(m, nn.Embedding) and m.padding_idx is not None:
                m.weight.data[m.padding_idx].zero_()

    def _rotations(self, T: int | torch.Tensor, dev):
        """Positions 0 … T − 1, ou tenseur de positions B × T (cos, sin : B × 1 × T × dh/2)."""
        dh = self.t.dimension // self.t.tetes
        f = self.t.rope_base ** (-torch.arange(0, dh, 2, device=dev, dtype=torch.float32) / dh)
        if isinstance(T, torch.Tensor):
            ang = T.float()[..., None] * f
            return ang.cos()[:, None], ang.sin()[:, None]
        ang = torch.arange(T, device=dev, dtype=torch.float32)[:, None] * f
        return ang.cos(), ang.sin()

    def plonger(self, lot: LotB) -> torch.Tensor:
        x = self.emb(lot.input_ids)
        for i, e in enumerate(self.attr):
            x = x + e(lot.num_attr[..., i])
        return x

    def forward(self, lot: LotB, x: torch.Tensor | None = None) -> torch.Tensor:
        """États cachés de la dernière couche, après la norme : B × T × d. `x` : vecteurs
        d'entrée déjà calculés (sinon `plonger`)."""
        x = self.plonger(lot) if x is None else x
        cos, sin = self._rotations(x.shape[1], x.device)
        vis = visibles(lot.segment)
        r = Relations(lot.name_idx, lot.prop_idx, lot.val_idx, lot.name_idx, lot.prop_idx,
                      lot.val_idx, lot.NN, lot.PP, vis)  # fmt: skip
        cache = ~vis[:, None]
        for c, delta in zip(self.couches, self.delta, strict=True):
            biais = biais_dense(delta, r)
            x = c(x, cos, sin, biais.masked_fill(cache, torch.finfo(biais.dtype).min))
        return self.norme(x)

    def logits(self, h: torch.Tensor) -> torch.Tensor:
        """Tête de langage liée aux vecteurs d'entrée."""
        return h @ self.emb.weight.T

    def groupes(self, decroissance: float) -> list[dict]:
        """§13 : pas de décroissance de poids sur δ, les normes et les vecteurs d'entrée
        (ni sur les scalaires τ, b)."""
        sans = {id(self.delta), id(self.emb.weight)} | {id(e.weight) for e in self.attr}
        avec, autres = [], []
        for p in self.parameters():
            (avec if p.dim() >= 2 and id(p) not in sans else autres).append(p)
        return [{"params": avec, "weight_decay": decroissance},
                {"params": autres, "weight_decay": 0.0}]  # fmt: skip


def attributs_b(icfg) -> tuple[int, int, int, int]:
    """Classes des 4 attributs (`encode.Vocabulaire.attributs`), 0 compris."""
    from ccm.schema import PrecisionDate

    a = icfg.anonymiseur
    lo, hi = a.grandeur
    return a.unites_max + 2 + len(PrecisionDate), hi - lo + 3, a.rang_max + 2, 4
