"""Exemples de génération libre de B pré-entraîné, pour voir ce qui sort à ce stade.

Mode causal, tête de langage seule (pointeurs et attributs ignorés : un slot généré reste
affiché tel quel, ⟨PER⟩, ⟨NUM⟩…). Tirage avec température et noyau (top-p), graine fixe.
"""

import torch

from ccm.data.pretrain.exemples import Jetons
from ccm.eval.canaris_b import _lot
from ccm.model.b import ModeleB

DEBUTS = (
    "La Révolution française a commencé en",
    "Le tribunal a jugé que",
    "La photosynthèse est un processus par lequel",
    "Il était une fois, dans un petit village,",
    "The European Parliament adopted",
)


@torch.no_grad()
def generer(modele: ModeleB, j: Jetons, debut: str, n: int = 120, temperature: float = 0.8,
            top_p: float = 0.9, graine: int = 0) -> str:  # fmt: skip
    dev = next(modele.parameters()).device
    g = torch.Generator(device=dev).manual_seed(graine)
    ids = [j.bos, *j.tok.encode(debut).ids]
    k = len(ids)
    for _ in range(n):
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            lp = modele.logits(modele(_lot([ids], dev))[:, -1]).float()[0]
        p = torch.softmax(lp / temperature, -1)
        tri, idx = p.sort(descending=True)
        garde = tri.cumsum(0) - tri < top_p
        choix = idx[garde][torch.multinomial(tri[garde], 1, generator=g)]
        ids.append(int(choix))
    return j.tok.decode(ids[k:], skip_special_tokens=False)


def exemples(modele: ModeleB, j: Jetons, debuts=DEBUTS, **kw) -> list[dict]:
    return [{"debut": d, "suite": generer(modele, j, d, **kw)} for d in debuts]
