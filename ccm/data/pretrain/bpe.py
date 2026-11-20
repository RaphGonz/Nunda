"""Tokenizer de B (SPEC.md §8) : BPE par octets, 32 000 jetons, casse gardée, entraîné sur le
corpus déjà anonymisé (`final/`). Il ne voit aucun nom détecté : chaque marqueur ⟦k⟧ devient le
jeton de son slot (⟨PER⟩ … ⟨DATE⟩). Les jetons spéciaux viennent en tête du vocabulaire.

Seule une part des fenêtres sert (tirage par graine sur l'id) : la mémoire de l'entraînement
du BPE croît avec le nombre de mots distincts.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path

from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

from ccm.data.pretrain.etat import ecrire_atomique, lire_lignes, tirage

STRUCTURE = ["[BOS]", "[H]", "[/H]", "[Q]", "[/Q]", "[REL]", "[/REL]", "[P]", "[/P]",
             "[SORTIE]", "[MASK]", "[NOUVEAU]"]  # fmt: skip
SLOTS = {t: f"⟨{t}⟩" for t in ("PER", "ORG", "LIEU", "REF", "AUTRE", "NUM", "DATE")}
SPECIAUX = STRUCTURE + list(SLOTS.values())

_MARQUEUR = re.compile(r"⟦(\d+)⟧")


def slot(marque: dict) -> str:
    """Jeton du slot d'une marque (`MarqueNom` ou `MarqueNombre`, en dictionnaire)."""
    return SLOTS[marque["type"] if marque["genre"] == "NOM" else marque["genre"]]


def texte_bpe(texte: str, marques: list[dict]) -> str:
    """Texte d'une fenêtre, chaque marqueur ⟦k⟧ remplacé par le jeton de son slot."""
    return _MARQUEUR.sub(lambda m: slot(marques[int(m.group(1))]), texte)


def textes(paquets: list[Path], part: float, graine: int) -> Iterator[str]:
    """Textes des fenêtres tirées (`part`), paquet par paquet."""
    for p in paquets:
        for f in lire_lignes(p):
            if tirage(graine, "bpe", f["id"]) < part:
                yield texte_bpe(f["texte"], json.loads(f["marques"]))


def nouveau(vocabulaire: int) -> tuple[Tokenizer, trainers.BpeTrainer]:
    tok = Tokenizer(models.BPE())
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    entraineur = trainers.BpeTrainer(
        vocab_size=vocabulaire, min_frequency=2, special_tokens=SPECIAUX,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(), show_progress=False,
    )  # fmt: skip
    return tok, entraineur


def entrainer(paquets: list[Path], sortie: Path, vocabulaire: int, part: float, graine: int
              ) -> dict:  # fmt: skip
    """Entraîne le BPE et écrit `tokenizer.json` et `bpe.json` (comptes) dans `sortie`."""
    tok, entraineur = nouveau(vocabulaire)
    n = {"fenetres": 0, "caracteres": 0}

    def flux():
        for t in textes(paquets, part, graine):
            n["fenetres"] += 1
            n["caracteres"] += len(t)
            yield t

    tok.train_from_iterator(flux(), trainer=entraineur)
    sortie.mkdir(parents=True, exist_ok=True)
    ecrire_atomique(sortie / "tokenizer.json", tok.to_str().encode())
    bilan = {"vocabulaire": tok.get_vocab_size(), "part": part, "graine": graine,
             "paquets": len(paquets), **n}  # fmt: skip
    ecrire_atomique(sortie / "bpe.json", json.dumps(bilan, indent=1).encode())
    return bilan


def charger(dossier: Path) -> Tokenizer:
    return Tokenizer.from_file(str(dossier / "tokenizer.json"))
