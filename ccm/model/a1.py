"""Prototype A1 (SPEC.md §9, §13) : A0 sans l'en-tête [REL], relations données par des
biais d'attention (`attention.py`, version dense). δ : couches × têtes × 24, à zéro au
départ ; A1 à son départ calcule donc exactement A0 sur une entrée sans en-tête.

A1 part du point de contrôle A0 (`depuis_a0`). Il garde la table de jetons nouveaux de A0
(mêmes identifiants) : les entrées sont encodées comme en A0, puis l'en-tête est retiré
(`sans_rel`) ; les lignes de [REL], [/REL] et ⟨R:…⟩ ne servent plus. Le biais est dense
(B × têtes × T × T par couche) : contexte limité à `T_MAX` jetons."""

import dataclasses
from pathlib import Path

import numpy as np
import torch

from ccm.anonymize.encode import Encodage, Vocabulaire
from ccm.model.a0 import ModeleA0
from ccm.model.attention import N_REL, Etat, Relations, envelopper

T_MAX = 2500  # §9 : « Le biais est dense : limiter le contexte à 2 500 jetons. »


def sans_rel(enc: Encodage, voc: Vocabulaire) -> Encodage:
    """Encodage de A0 → entrée de A1 : l'en-tête [REL] … [/REL] est retiré, les positions
    qui le suivent reculent d'autant. Les tables (NN, PP, indices) restent."""
    ids = enc.input_ids
    debut = np.flatnonzero(ids == voc.ids["[REL]"])
    if not len(debut):
        return enc
    a, b = int(debut[0]), int(np.flatnonzero(ids == voc.ids["[/REL]"])[0]) + 1
    garde = np.r_[0:a, b : len(ids)]
    recule = lambda p: np.where(p >= b, p - (b - a), p)  # noqa: E731
    return dataclasses.replace(
        enc,
        **{c: getattr(enc, c)[garde] for c in
           ("input_ids", "segment", "prop_idx", "name_idx", "val_idx", "num_attr")},
        fin_prop=recule(enc.fin_prop), pos_mention=recule(enc.pos_mention),
        pos_nombre=recule(enc.pos_nombre),
    )  # fmt: skip


def _carre(tables: list[np.ndarray], dev) -> torch.Tensor:
    n = max(len(t) for t in tables)
    out = torch.zeros(len(tables), n, n, dtype=torch.long)
    for i, t in enumerate(tables):
        out[i, : len(t), : len(t)] = torch.as_tensor(t)
    return out.to(dev)


class ModeleA1(ModeleA0):
    def __init__(self, tronc, voc: Vocabulaire):
        super().__init__(tronc, voc)
        c = tronc.config
        self.delta = torch.nn.Parameter(torch.zeros(c.num_hidden_layers, c.num_attention_heads,
                                                    N_REL))  # fmt: skip
        self.etat = Etat(self.delta)
        self._crochets = envelopper(tronc, self.etat)

    def regler(self, encs, s0s, l1, l2) -> None:
        if encs is None:
            self.etat.relations = None
            return
        if max(len(e.input_ids) for e in encs) > T_MAX:
            raise ValueError(f"T > {T_MAX} : biais dense trop grand (§9)")
        dev = self.delta.device
        B = len(encs)
        idx = torch.zeros(3, B, l1 + l2, dtype=torch.long)  # nom, proposition, valeur
        valide = torch.zeros(B, l1 + l2, dtype=torch.bool)
        pos = torch.zeros(B, l1 + l2, dtype=torch.long)
        pos[:, :l1] = torch.arange(l1)
        for b, (e, s0) in enumerate(zip(encs, s0s, strict=True)):
            t = torch.as_tensor(np.stack([e.name_idx, e.prop_idx, e.val_idx]))
            idx[:, b, :s0], valide[b, :s0] = t[:, :s0], True
            if l2:
                n = len(e.input_ids) - s0
                idx[:, b, l1 : l1 + n], valide[b, l1 : l1 + n] = t[:, s0:], True
                pos[b, l1:] = s0 + torch.arange(l2)
        idx, valide, pos = idx.to(dev), valide.to(dev), pos.to(dev)
        q = slice(l1, l1 + l2) if l2 else slice(0, l1)
        k = slice(0, l1 + l2)
        visible = valide[:, None, k] & (pos[:, None, k] <= pos[:, q, None])
        self.etat.relations = Relations(
            *idx[:, :, q], *idx[:, :, k],
            NN=_carre([e.NN for e in encs], dev), PP=_carre([e.PP for e in encs], dev),
            visible=visible,
        )  # fmt: skip


def optimiseur(modele: ModeleA1, lr_lora=2e-4, lr_nouveaux=1e-3, decroissance=0.01):
    """Comme A0 (§13), δ avec les modules nouveaux mais sans décroissance de poids."""
    lora = [p for p in modele.tronc.parameters() if p.requires_grad]
    autres = [p for p in modele.nouveaux_modules() if p is not modele.delta]
    return torch.optim.AdamW(
        [{"params": lora, "lr": lr_lora}, {"params": autres, "lr": lr_nouveaux},
         {"params": [modele.delta], "lr": lr_nouveaux, "weight_decay": 0.0}],
        betas=(0.9, 0.999), weight_decay=decroissance,
    )  # fmt: skip


def depuis_a0(modele: ModeleA1, chemin: Path) -> int:
    """Poids entraînés d'un point de contrôle A0 (tous, sauf δ qui reste à zéro) ; rend son
    pas. L'optimiseur repart de zéro."""
    etat = torch.load(chemin, map_location="cpu", weights_only=True)
    poids = etat["poids"]
    attendus = {n for n, p in modele.named_parameters() if p.requires_grad} - {"delta"}
    if set(poids) != attendus:
        raise ValueError(f"poids différents : {sorted(set(poids) ^ attendus)[:5]}")
    modele.load_state_dict(poids, strict=False)
    return etat["pas"]


def charger_smollm_a1(voc: Vocabulaire, nom: str = "HuggingFaceTB/SmolLM2-360M") -> ModeleA1:
    from transformers import AutoModel

    from ccm.model.a0 import avec_lora

    tronc = AutoModel.from_pretrained(nom, dtype=torch.bfloat16, attn_implementation="sdpa")
    if tronc.get_input_embeddings().num_embeddings != voc.taille:
        raise ValueError("taille du tokenizer différente de celle du vocabulaire")
    m = ModeleA1(avec_lora(tronc), voc)
    for p in m.parameters():
        if p.requires_grad:
            p.data = p.data.float()
    return m
