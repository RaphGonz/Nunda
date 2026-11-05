"""Réglage fin de A0 (SPEC.md §13) : boucle d'entraînement, un contexte par pas avant
accumulation. `python -m ccm.train.a0` : surapprentissage voulu sur 8 exemples du corpus
synthétique (contrôle que la perte baisse)."""

import json
import sys
import time
from collections.abc import Sequence

import torch

from ccm.model.a0 import ModeleA0, optimiseur, perte
from ccm.train.chargeur import Tirage


def entrainer(modele: ModeleA0, tirages: Sequence[Tirage], pas: int, accumulation: int = 1,
              journal=None, **lr) -> list[float]:  # fmt: skip
    """`pas` mises à jour, exemples pris en boucle ; rend la perte moyenne de chaque pas."""
    opt = optimiseur(modele, **lr)
    dev = modele.lex.weight.device
    bf16 = dev.type == "cuda"
    modele.train()
    pertes, k = [], 0
    for i in range(pas):
        total = 0.0
        for _ in range(accumulation):
            t = tirages[k % len(tirages)]
            k += 1
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=bf16):
                p = perte(modele(t.encodage), t.encodage, t.exemple.justificatives)
            (p["total"] / accumulation).backward()
            total += p["total"].item() / accumulation
        torch.nn.utils.clip_grad_norm_(modele.parameters(), 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        pertes.append(total)
        if journal:
            journal(i, total)
    return pertes


def _huit_exemples(voc, decouper, n=8):
    from ccm.config import load_config
    from ccm.data.worldgen.monde import generer_monde
    from ccm.data.worldgen.pieces import rediger_dossier
    from ccm.data.worldgen.questions import poser_questions
    from ccm.train.chargeur import Chargeur, SourceSynthetique

    icfg, wcfg = load_config("ingest"), load_config("worldgen")
    d = rediger_dossier(generer_monde(0, "entrainement", wcfg, frozenset()), wcfg)
    src = SourceSynthetique([(d, poser_questions(d, wcfg))], icfg)
    ch = Chargeur({"synthetique": src}, load_config("finetune").chargeur, icfg,
                  load_config("search"), load_config("grammar"), voc, decouper)  # fmt: skip
    out = []
    for t in ch.epoque(0, 4 * n):
        if len(out) < n:
            out.append(t)
    return out


def main(pas: int = 200) -> None:
    from transformers import AutoTokenizer

    from ccm.anonymize.encode import Vocabulaire
    from ccm.config import load_config
    from ccm.model.a0 import charger_smollm

    nom = "HuggingFaceTB/SmolLM2-360M"
    tok = AutoTokenizer.from_pretrained(nom)
    voc = Vocabulaire(load_config("model_a0"), load_config("ingest"), len(tok))
    tirages = _huit_exemples(voc, lambda s: tok(s, add_special_tokens=False).input_ids)
    print("exemples :", [(t.genre, len(t.encodage.input_ids), len(t.exemple.cible))
                         for t in tirages], flush=True)  # fmt: skip
    torch.manual_seed(0)
    modele = charger_smollm(voc, nom).to("cuda" if torch.cuda.is_available() else "cpu")
    t0 = time.time()
    pertes = entrainer(modele, tirages, pas, accumulation=len(tirages),
                       journal=lambda i, x: print(f"pas {i} perte {x:.4f}", flush=True)
                       if i % 10 == 0 or i == pas - 1 else None)  # fmt: skip
    print(json.dumps({"premiere": pertes[0], "derniere": pertes[-1], "secondes": time.time() - t0}))


if __name__ == "__main__":
    main(*map(int, sys.argv[1:]))
