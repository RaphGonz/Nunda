"""Export pour Hugging Face (décision de Raphael du 2026-11-26 : poids ouverts, pour la
recherche). Écrit un dossier par dépôt dans `sortie` ; l'envoi se fait à la main
(`huggingface-cli upload`).

- `nunda-niveau0` : corpus synthétique de niveau 0 (entraînement, validation), inventé.
- `nunda-a0`, `nunda-a1` : poids entraînés (LoRA sur SmolLM2-360M, têtes, vecteurs nouveaux).
- `nunda-b-s` : B-S réglé sur la citation (tous les poids) et son BPE.
- `nunda-corpus-anonymise` (`python -m ccm.publier corpus [sortie]`) : corpus de
  pré-entraînement de B (`pretrain/final`), sans les fenêtres à canaris (naturels : documents
  porteurs ; forcés : nom en clair) ni Judilibre (CGU : ne pas altérer les décisions).

Seuls les poids entraînés sont gardés (`safetensors`), sans l'état de l'optimiseur.

`python -m ccm.publier [sortie]` (par défaut `D:/Nunda-hf`)."""

import json
import re
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


EXCLUES = {"judilibre"}
COLONNES = ["id", "document", "source", "langue", "texte", "texte_slots", "marques", "jetons"]


def slots(texte: str, marques: list[dict]) -> str:
    """⟦i⟧ → ⟨PER 3⟩ (nom), ⟨DATE⟩, ⟨NUM⟩."""

    def un(m):
        k = marques[int(m.group(1))]
        return f"⟨{k['type']} {k['nom']}⟩" if k["genre"] == "NOM" else f"⟨{k['genre']}⟩"

    return re.sub(r"⟦(\d+)⟧", un, texte)


def filtre_canaris(canaris: list[dict]):
    """Rend `garder(ligne)` : faux pour une fenêtre d'un document à canari naturel, ou qui
    contient le nom en clair d'un canari forcé."""
    naturels = {d for c in canaris if c["genre"] == "naturel" for d in c["documents"]}
    noms = re.compile("|".join(re.escape(c["nom"]) for c in canaris if c["genre"] == "force"))
    return lambda x: x["document"] not in naturels and not noms.search(x["texte"])


def corpus_anonymise(sortie: str = "D:/Nunda-hf") -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from ccm.config import load_config

    racine = load_config("donnees").racine
    canaris = json.loads((racine / "canaris" / "canaris.json").read_text("utf-8"))
    garder = filtre_canaris(canaris)
    dossier = Path(sortie) / "nunda-corpus-anonymise" / "data"
    dossier.mkdir(parents=True, exist_ok=True)
    bilan = {"gardees": 0, "canaris": 0, "exclues": 0, "jetons": 0}
    for p in sorted((racine / "pretrain" / "final").glob("paquet-*.parquet")):
        lignes = []
        for x in pq.read_table(p).to_pylist():
            if x["source"] in EXCLUES:
                bilan["exclues"] += 1
            elif not garder(x):
                bilan["canaris"] += 1
            else:
                x["texte_slots"] = slots(x["texte"], json.loads(x["marques"]))
                lignes.append({k: x[k] for k in COLONNES})
                bilan["jetons"] += x["jetons"]
        bilan["gardees"] += len(lignes)
        pq.write_table(pa.Table.from_pylist(lignes), dossier / p.name, compression="zstd")
        print(p.name, bilan, flush=True)
    return bilan


def main(sortie: str = "D:/Nunda-hf") -> dict:
    s = Path(sortie)
    bilan = {"nunda-niveau0": corpus(s / "nunda-niveau0")}
    for nom in POINTS:
        bilan[nom] = modele(nom, s / nom)
    print(json.dumps(bilan, indent=1))
    return bilan


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["corpus"]:
        corpus_anonymise(*a[1:2])
    else:
        main(*a[:1])
