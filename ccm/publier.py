"""Export pour Hugging Face (décision de Raphael du 2026-11-26 : poids ouverts, pour la
recherche). Écrit un dossier par dépôt dans `sortie` ; l'envoi se fait à la main
(`huggingface-cli upload`).

- `nunda-niveau0` : corpus synthétique de niveau 0 (entraînement, validation), inventé.
- `nunda-a0`, `nunda-a1` : poids entraînés (LoRA sur SmolLM2-360M, têtes, vecteurs nouveaux).
- `nunda-b-s` : B-S réglé sur la citation (tous les poids) et son BPE.

Seuls les poids entraînés sont gardés (`safetensors`), sans l'état de l'optimiseur.

`python -m ccm.publier [sortie]` (par défaut `D:/Nunda-hf`)."""

import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors.torch import save_file

RACINE = Path(__file__).resolve().parents[1]
RUNS = RACINE / "runs"
POINTS = {
    "nunda-a0": RUNS / "2026-11-06-a0" / "pas-018124.pt",
    "nunda-a1": RUNS / "2026-11-08-a1" / "pas-008378.pt",
    "nunda-b-s": RUNS / "2026-11-25-b-fin" / "pas-020625.pt",
}
CONFIGS = {
    "nunda-a0": ["model_a0", "finetune", "grammar", "ingest", "search"],
    "nunda-a1": ["model_a0", "model_a1", "finetune", "grammar", "ingest", "search"],
    "nunda-b-s": ["model_b_s", "pretrain", "finetune", "grammar", "ingest", "search"],
}
EVALS = {
    "nunda-a0": RUNS / "2026-11-06-a0" / "eval-pas-018124-corrige",
    "nunda-a1": RUNS / "2026-11-08-a1" / "eval-pas-008378-corrige",
    "nunda-b-s": RUNS / "2026-11-25-b-fin" / "eval-pas-020625-corrige",
}


def poids(point: Path) -> tuple[dict[str, torch.Tensor], int]:
    """Poids entraînés d'un point de contrôle (sans optimiseur) et son pas."""
    etat = torch.load(point, map_location="cpu", weights_only=True)
    return {k: v.detach().contiguous() for k, v in etat["poids"].items()}, etat["pas"]


def modele(nom: str, dossier: Path) -> dict:
    dossier.mkdir(parents=True, exist_ok=True)
    w, pas = poids(POINTS[nom])
    save_file(w, dossier / "model.safetensors", metadata={"pas": str(pas)})
    (dossier / "configs").mkdir(exist_ok=True)
    for c in CONFIGS[nom]:
        shutil.copy(RACINE / "configs" / f"{c}.yaml", dossier / "configs")
    (dossier / "eval").mkdir(exist_ok=True)
    for f in ("rapport.md", "resultats.json"):
        shutil.copy(EVALS[nom] / f, dossier / "eval" / f)
    if nom == "nunda-b-s":
        shutil.copytree(RACINE / "runs" / "modeles" / "bpe-b", dossier / "tokenizer",
                        dirs_exist_ok=True)  # fmt: skip
    return {"poids": len(w), "parametres": sum(v.numel() for v in w.values()), "pas": pas}


def corpus(dossier: Path) -> dict:
    out = {}
    for partie, src in (("entrainement", "niveau0"), ("validation", "niveau0-val")):
        shutil.copytree(RUNS / "corpus" / src / partie, dossier / partie, dirs_exist_ok=True)
        shutil.copy(RUNS / "corpus" / src / "controle.json", dossier / f"controle-{partie}.json")
        out[partie] = sum(1 for _ in (dossier / partie).iterdir())
    shutil.copy(RACINE / "configs" / "worldgen.yaml", dossier / "worldgen.yaml")
    return out


def main(sortie: str = "D:/Nunda-hf") -> dict:
    s = Path(sortie)
    bilan = {"nunda-niveau0": corpus(s / "nunda-niveau0")}
    for nom in POINTS:
        bilan[nom] = modele(nom, s / nom)
    print(json.dumps(bilan, indent=1))
    return bilan


if __name__ == "__main__":
    main(*sys.argv[1:2])
