"""Réglage fin de B (SPEC.md §9, §13) : le tronc pré-entraîné de B, les têtes de A0.

Entrée : `Encodage` de la variante B (`encode`, un vecteur par type de slot), découpé par
le BPE de B. Les jetons de `Vocabulaire` qui existent dans le BPE (structure, slots)
prennent leur vecteur pré-entraîné ; les autres (pièces, rangs, drapeaux, lexique, genres
des pointeurs) ont une table nouvelle.

Deux passes, comme A0. Passe 1 : l'entrée, jusqu'avant [SORTIE], bidirectionnelle
(prefix-LM) ; elle donne les vecteurs pointés (proposition : attention pooling sur ses
jetons, α = softmax(w · h_j), puis linéaire et RMSNorm ; nombre et mention : le slot) et
garde ses clés et valeurs. Passe 2 : la sortie seule, causale, qui voit toute l'entrée par
ce cache ; après un pointeur, l'entrée est le vecteur du genre (⟨PT:X⟩) + `W_in` × vecteur
pointé de la référence, avec le gradient. L'entrée ne voit jamais la sortie : c'est le même
calcul qu'une seule passe sur toute la séquence.
"""

import torch
from torch import nn

from ccm.anonymize.encode import Encodage, Vocabulaire
from ccm.grammar.lexicon import LEXIQUE_COMPLET
from ccm.model.a0 import Pointeur, Sortie
from ccm.model.attention import Relations, biais_dense
from ccm.model.b import LotB, ModeleB, visibles


def _carres(tables: list, dev) -> torch.Tensor:
    n = max(len(t) for t in tables)
    out = torch.zeros(len(tables), n, n, dtype=torch.long, device=dev)
    for i, t in enumerate(tables):
        out[i, : len(t), : len(t)] = torch.as_tensor(t, device=dev)
    return out


class ModeleBFin(nn.Module):
    def __init__(self, tronc: ModeleB, voc: Vocabulaire, tok, abandon: float = 0.1):
        """`tok` : BPE de B (`tokenizers.Tokenizer`)."""
        super().__init__()
        self.tronc, self.voc = tronc, voc
        d = tronc.t.dimension
        for c in tronc.couches:
            c.abandon = abandon
        carte, nouveaux = [], 0
        for j in voc.jetons:
            k = tok.token_to_id(j)
            carte.append(k if k is not None else tronc.emb.num_embeddings + nouveaux)
            nouveaux += k is None
        self.register_buffer("carte", torch.tensor(carte), persistent=False)
        self.nouveaux = nn.Embedding(nouveaux, d)
        nn.init.normal_(self.nouveaux.weight, std=tronc.emb.weight.detach().float().std().item())
        self.w_in = nn.Linear(d, d, bias=False)
        self.pool = nn.Linear(d, 1, bias=False)
        self.prop = nn.Sequential(nn.Linear(d, d, bias=False), nn.RMSNorm(d))
        self.lex = nn.Linear(d, len(LEXIQUE_COMPLET), bias=False)
        self.p, self.n, self.m = Pointeur(d), Pointeur(d), Pointeur(d)
        self.select = nn.Linear(d, 1)

    def nouveaux_modules(self) -> list[nn.Parameter]:
        return [p for n, p in self.named_parameters() if not n.startswith("tronc.")]

    def plonger(self, ids: torch.Tensor, attr: torch.Tensor) -> torch.Tensor:
        """Identifiants du BPE (< taille) ou de `Vocabulaire` → vecteurs, plus les attributs."""
        taille, emb = self.voc.taille, self.tronc.emb
        ids = torch.where(ids >= taille, self.carte[(ids - taille).clamp(min=0)], ids)
        ancien = ids < emb.num_embeddings
        x = emb(ids.clamp(max=emb.num_embeddings - 1))
        x = torch.where(
            ancien[..., None], x, self.nouveaux((ids - emb.num_embeddings).clamp(min=0))
        )
        return x + sum(e(attr[..., i]) for i, e in enumerate(self.tronc.attr))

    def forward(self, enc: Encodage) -> Sortie:
        return self.lot([enc])[0]

    def lot(self, encs: list[Encodage]) -> list[Sortie]:
        """Plusieurs contextes en une passe, complétés à droite (segment −1)."""
        dev = self.lex.weight.device
        t = lambda a: torch.as_tensor(a, device=dev)  # noqa: E731
        L, tr = len(LEXIQUE_COMPLET), self.tronc
        s0s = [int((enc.segment == 2).nonzero()[0][0]) for enc in encs]
        l1 = max(s0s)
        l2 = max(len(e.input_ids) - s0 for e, s0 in zip(encs, s0s, strict=True))
        B = len(encs)

        def col(nom, fin, long, plein=0, forme=()):
            out = torch.full((B, long, *forme), plein, dtype=torch.long, device=dev)
            for b, (e, s0) in enumerate(zip(encs, s0s, strict=True)):
                a = getattr(e, nom).reshape(len(e.input_ids), *forme)
                a = a[:s0] if fin else a[s0:]
                out[b, : len(a)] = t(a)
            return out

        NN, PP = _carres([e.NN for e in encs], dev), _carres([e.PP for e in encs], dev)
        lots = [LotB(col("input_ids", True, l1), col("segment", True, l1, -1),
                     col("prop_idx", True, l1), col("name_idx", True, l1),
                     col("val_idx", True, l1), col("num_attr", True, l1, 0, (4,)), NN, PP),
                LotB(col("input_ids", False, l2), col("segment", False, l2, -1),
                     col("prop_idx", False, l2), col("name_idx", False, l2),
                     col("val_idx", False, l2), col("num_attr", False, l2, 0, (4,)), NN,
                     PP)]  # fmt: skip
        a, s = lots

        # Passe 1 : l'entrée.
        x1 = self.plonger(a.input_ids, a.num_attr)
        cos, sin = tr._rotations(l1, dev)
        vis = visibles(a.segment)
        r = Relations(a.name_idx, a.prop_idx, a.val_idx, a.name_idx, a.prop_idx, a.val_idx, NN,
                      PP, vis)  # fmt: skip
        caches: list = []
        for c, delta in zip(tr.couches, tr.delta, strict=True):
            biais = biais_dense(delta, r)
            x1 = c(x1, cos, sin, biais.masked_fill(~vis[:, None], torch.finfo(biais.dtype).min),
                   garder=caches)  # fmt: skip
        h1 = tr.norme(x1)

        # Vecteurs pointés, puis entrée de la sortie.
        x2 = self.plonger(s.input_ids, s.num_attr)
        pointes, ajouts = [], torch.zeros_like(x2)
        for b, (enc, s0) in enumerate(zip(encs, s0s, strict=True)):
            h = h1[b, :s0]
            props = t(enc.prop_idx[:s0]) * t(enc.segment[:s0] == 1)
            P = len(enc.fin_prop)
            dans = props[None, :] == torch.arange(1, P + 1, device=dev)[:, None]  # P × s0
            alpha = self.pool(h).squeeze(-1).float().masked_fill(~dans, float("-inf"))
            r_p = self.prop((alpha.softmax(-1).to(h.dtype) @ h) if P else h[:0])
            h_n, h_m = h[t(enc.pos_nombre)], h[t(enc.pos_mention)]
            pointes.append((r_p, h_n, h_m))
            cible = t(enc.cible)
            pt = (cible >= L).nonzero().squeeze(-1)
            if len(pt):
                v = torch.cat([r_p, h_n, h_m])
                ajouts[b, 1 + pt] = self.w_in(v[cible[pt] - L]).to(ajouts.dtype)
        x2 = x2 + ajouts

        # Passe 2 : la sortie ; elle voit l'entrée (cache) et, en causal, la sortie.
        pos = t(s0s)[:, None] + torch.arange(l2, device=dev)
        cos, sin = tr._rotations(pos, dev)
        k_ok = (a.segment >= 0)[:, None, :].expand(B, l2, l1)
        causal = torch.ones(l2, l2, dtype=torch.bool, device=dev).tril()
        vis2 = torch.cat([k_ok, (s.segment >= 0)[:, None, :] & causal], 2)
        r2 = Relations(s.name_idx, s.prop_idx, s.val_idx, torch.cat([a.name_idx, s.name_idx], 1),
                       torch.cat([a.prop_idx, s.prop_idx], 1),
                       torch.cat([a.val_idx, s.val_idx], 1), NN, PP, vis2)  # fmt: skip
        for c, delta, kv in zip(tr.couches, tr.delta, caches, strict=True):
            biais = biais_dense(delta, r2)
            x2 = c(x2, cos, sin, biais.masked_fill(~vis2[:, None], torch.finfo(biais.dtype).min),
                   avant=kv)  # fmt: skip
        h2 = tr.norme(x2)

        out = []
        for b, (enc, (r_p, h_n, h_m)) in enumerate(zip(encs, pointes, strict=True)):
            ht = h2[b, : len(enc.cible)]
            logits = torch.cat([self.lex(ht), self.p(ht, r_p), self.n(ht, h_n), self.m(ht, h_m)], 1)
            if enc.masque is not None:
                logits = logits.float().masked_fill(~t(enc.masque), float("-inf"))
            out.append(Sortie(logits, self.select(r_p).squeeze(-1)))
        return out


def optimiseur(modele: ModeleBFin, lr_tronc=1e-4, lr_tetes=5e-4, decroissance=0.05):
    """AdamW, bêtas 0,9 et 0,999 (§13, phase 6) : tronc à `lr_tronc`, têtes et vecteurs
    nouveaux à `lr_tetes` ; décroissance sur les matrices, aucune sur δ ni sur les normes et
    les scalaires."""
    groupes = []
    for params, lr in (
        (modele.tronc.parameters(), lr_tronc),
        (modele.nouveaux_modules(), lr_tetes),
    ):
        avec, sans = [], []
        for p in params:
            (avec if p.dim() >= 2 and p is not modele.tronc.delta else sans).append(p)
        groupes += [{"params": avec, "lr": lr, "weight_decay": decroissance},
                    {"params": sans, "lr": lr, "weight_decay": 0.0}]  # fmt: skip
    return torch.optim.AdamW(groupes, betas=(0.9, 0.999))
