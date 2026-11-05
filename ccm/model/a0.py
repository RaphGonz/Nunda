"""Prototype A0 (SPEC.md §9) et perte de réglage fin (§13).

Tronc : modèle pré-entraîné (SmolLM2-360M) avec LoRA de rang 16 sur l'attention et le MLP.
Les jetons nouveaux (`Vocabulaire`, dont l'en-tête [REL] de A0) ont leur propre table ;
l'entrée passe par `inputs_embeds`. Les attributs d'un nombre (`num_attr`) s'ajoutent au
vecteur de son slot.

Deux passes. La première encode l'entrée, jusqu'avant [SORTIE] : ses états cachés donnent
les vecteurs pointés (proposition : [/P], linéaire, RMSNorm ; nombre et mention : le slot).
La seconde lit la sortie avec le cache de la première ; après un pointeur, l'entrée est le
vecteur du genre (⟨PT:X⟩) + `W_in` × vecteur pointé de la référence, avec le gradient. Le
masque est causal : la première passe ne voit jamais la sortie, comme en une seule passe.
"""

import math
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import nn

from ccm.anonymize.encode import Encodage, Vocabulaire
from ccm.grammar.lexicon import LEXIQUE_COMPLET

D_POINTEUR = 256
CIBLES_LORA = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
ATTR_MAX = 256  # cases de chaque colonne de `num_attr`


def avec_lora(tronc: nn.Module, rang: int = 16, alpha: int = 32, abandon: float = 0.05):
    from peft import LoraConfig, get_peft_model

    cfg = LoraConfig(r=rang, lora_alpha=alpha, lora_dropout=abandon, target_modules=CIBLES_LORA)
    return get_peft_model(tronc, cfg)


class Pointeur(nn.Module):
    """s = τ · (A h_t) · (B v) / √256 + b ; τ et b scalaires de la famille (C12)."""

    def __init__(self, d: int):
        super().__init__()
        self.a = nn.Linear(d, D_POINTEUR, bias=False)
        self.b = nn.Linear(d, D_POINTEUR, bias=False)
        self.tau = nn.Parameter(torch.ones(()))
        self.biais = nn.Parameter(torch.zeros(()))

    def forward(self, h: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
        return self.tau * self.a(h) @ self.b(v).T / math.sqrt(D_POINTEUR) + self.biais


@dataclass
class Sortie:
    logits: torch.Tensor  # S × (L + P + K + M), masque appliqué
    selection: torch.Tensor  # P : logit de P(p utile)


class ModeleA0(nn.Module):
    def __init__(self, tronc: nn.Module, voc: Vocabulaire):
        """`tronc` : modèle de base sans tête (avec ou sans LoRA), qui accepte
        `inputs_embeds`, `past_key_values` et rend `last_hidden_state`."""
        super().__init__()
        self.tronc, self.voc = tronc, voc
        base = tronc.get_input_embeddings()
        d = base.embedding_dim
        self.nouveaux = nn.Embedding(len(voc.jetons), d)
        self.attributs = nn.ModuleList(nn.Embedding(ATTR_MAX, d, padding_idx=0) for _ in range(4))
        std = base.weight.detach().float().std().item()
        for e in (self.nouveaux, *self.attributs):
            nn.init.normal_(e.weight, std=std)
        for e in self.attributs:
            e.weight.data[0].zero_()
        self.w_in = nn.Linear(d, d, bias=False)
        self.prop = nn.Sequential(nn.Linear(d, d, bias=False), nn.RMSNorm(d))
        self.lex = nn.Linear(d, len(LEXIQUE_COMPLET), bias=False)
        self.p, self.n, self.m = Pointeur(d), Pointeur(d), Pointeur(d)
        self.select = nn.Linear(d, 1)

    def nouveaux_modules(self) -> list[nn.Parameter]:
        return [p for n, p in self.named_parameters() if not n.startswith("tronc.")]

    def plonger(self, ids: torch.Tensor, attr: torch.Tensor) -> torch.Tensor:
        taille = self.voc.taille
        base = self.tronc.get_input_embeddings()
        nouveau = ids >= taille
        x = base(ids.clamp(max=taille - 1))
        x = torch.where(nouveau[:, None], self.nouveaux((ids - taille).clamp(min=0)), x)
        return x + sum(e(attr[:, i]) for i, e in enumerate(self.attributs))

    def forward(self, enc: Encodage) -> Sortie:
        dev = self.lex.weight.device
        t = lambda a: torch.as_tensor(a, device=dev)  # noqa: E731
        ids, attr = t(enc.input_ids), t(enc.num_attr).reshape(-1, 4)
        if attr.max() >= ATTR_MAX:
            raise ValueError(f"attribut {attr.max().item()} ≥ {ATTR_MAX}")
        s0 = int((t(enc.segment) == 2).nonzero()[0])  # position de [SORTIE]
        x = self.plonger(ids, attr)

        # Passe 1 : l'entrée.
        o1 = self.tronc(inputs_embeds=x[None, :s0], use_cache=True)
        h = o1.last_hidden_state[0]
        r_p = self.prop(h[t(enc.fin_prop)])
        h_n, h_m = h[t(enc.pos_nombre)], h[t(enc.pos_mention)]
        pointes = torch.cat([r_p, h_n, h_m]).to(x.dtype)

        # Passe 2 : la sortie ; un pointeur reçoit son genre + W_in × vecteur pointé.
        L, S = len(LEXIQUE_COMPLET), len(enc.cible)
        x2 = x[s0:]  # [SORTIE], puis les S pas de référence
        cible = t(enc.cible)
        pt = cible >= L
        ajout = torch.zeros_like(x2[1:])
        ajout[pt] = self.w_in(pointes[cible[pt] - L]).to(x2.dtype)
        x2 = torch.cat([x2[:1], x2[1:] + ajout])
        pos = torch.arange(s0, len(ids), device=dev)[None]
        o2 = self.tronc(inputs_embeds=x2[None], past_key_values=o1.past_key_values,
                        position_ids=pos, use_cache=False)  # fmt: skip
        ht = o2.last_hidden_state[0, :S]

        logits = torch.cat([self.lex(ht), self.p(ht, r_p), self.n(ht, h_n), self.m(ht, h_m)], 1)
        if enc.masque is not None:
            logits = logits.float().masked_fill(~t(enc.masque), float("-inf"))
        return Sortie(logits, self.select(r_p).squeeze(-1))


def groupes(enc: Encodage) -> torch.Tensor:
    """Groupe de chaque colonne de l'espace : une mention prend le groupe de son nom
    (pointeur de nom, C1) ; toute autre colonne est seule dans le sien."""
    L, P, K = len(LEXIQUE_COMPLET), len(enc.fin_prop), len(enc.pos_nombre)
    g = torch.arange(len(enc.espace))
    noms = torch.as_tensor(enc.name_idx[enc.pos_mention])
    g[L + P + K :] = len(enc.espace) + noms
    return g


def perte(sortie: Sortie, enc: Encodage, justificatives: list[int]) -> dict[str, torch.Tensor]:
    """L = L_actions + 0,5 · L_sélection (§13). Un pas de mention : −log de la somme des
    probabilités des mentions autorisées du nom de référence."""
    logits = sortie.logits.float()
    dev = logits.device
    cible = torch.as_tensor(enc.cible, device=dev)
    g = groupes(enc).to(dev)
    meme = g[None, :] == g[cible][:, None]
    num = torch.logsumexp(logits.masked_fill(~meme, float("-inf")), -1)
    actions = (torch.logsumexp(logits, -1) - num).mean()

    sel = sortie.selection.float()
    y = torch.zeros_like(sel)
    y[torch.as_tensor(justificatives, dtype=torch.long, device=dev)] = 1
    pos = y.sum()
    poids = ((len(y) - pos) / pos).clamp(max=10) if pos else torch.ones((), device=dev)
    selection = F.binary_cross_entropy_with_logits(sel, y, pos_weight=poids)
    return {"total": actions + 0.5 * selection, "actions": actions, "selection": selection}


def optimiseur(modele: ModeleA0, lr_lora=2e-4, lr_nouveaux=1e-3, decroissance=0.01):
    """AdamW, bêtas 0,9 et 0,999 (§13) : LoRA à `lr_lora`, modules nouveaux à `lr_nouveaux`."""
    lora = [p for n, p in modele.tronc.named_parameters() if p.requires_grad]
    return torch.optim.AdamW(
        [{"params": lora, "lr": lr_lora}, {"params": modele.nouveaux_modules(), "lr": lr_nouveaux}],
        betas=(0.9, 0.999),
        weight_decay=decroissance,
    )


def charger_smollm(voc: Vocabulaire, nom: str = "HuggingFaceTB/SmolLM2-360M") -> ModeleA0:
    from transformers import AutoModel

    tronc = AutoModel.from_pretrained(nom, dtype=torch.float32)
    if tronc.get_input_embeddings().num_embeddings != voc.taille:
        raise ValueError("taille du tokenizer différente de celle du vocabulaire")
    return ModeleA0(avec_lora(tronc), voc)
