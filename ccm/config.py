"""Lecture des configurations YAML, validées par pydantic (SPEC.md §3).

Chaque fichier de `configs/` a sa classe. Les champs s'ajoutent phase par phase ;
une clé inconnue est une erreur.
"""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


class ConfigBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    description: str


class IngestConfig(ConfigBase):
    pass


class SearchConfig(ConfigBase):
    pass


class ModelConfig(ConfigBase):
    pass


class PretrainConfig(ConfigBase):
    pass


class FinetuneConfig(ConfigBase):
    pass


Intervalle = tuple[int, int]


class PartieCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dossiers: int
    graine: int
    reservoir: Literal["entrainement", "test"]


class PdfConfig(BaseModel):
    """Mise en page des pièces en PDF natif (points typographiques)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    largeur: float
    hauteur: float
    marge: float
    taille: float
    interligne: float
    espace_paragraphe: float
    colonnes: tuple[float, ...]
    marge_cellule: float


class RedactionConfig(BaseModel):
    """Pièces rédigées par gabarits (SPEC.md §12). Intervalles [min, max] inclus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pieces: Intervalle
    poids_pieces: dict[str, float]
    types_par_piece: dict[str, tuple[str, ...]]
    evenements_piece: Intervalle
    delai_piece_jours: Intervalle
    part_contradiction: float
    champs_contradiction: tuple[str, ...]
    decalage_heure_minutes: Intervalle
    formes_premiere: tuple[str, ...]
    formes_suite: tuple[str, ...]
    formes_societe: tuple[str, ...]
    sortie: str
    pdf: PdfConfig


class QuestionsConfig(BaseModel):
    """Questions et vérité terrain du corpus synthétique (SPEC.md §12, §10 bis)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    par_dossier: int
    parts: dict[str, float]
    conflit_par_dossier: int
    etapes: dict[int, float]
    calculs: tuple[str, ...]
    part_somme_une: float
    dialogues: dict[str, float]
    part_societe: float
    part_titre: float
    part_date: float
    part_preuve: float
    part_conflit_date: float
    essais: int


class WorldgenConfig(ConfigBase):
    """Générateur de monde (SPEC.md §12). Intervalles [min, max] inclus."""

    personnes: Intervalle
    societes: Intervalle
    lieux: Intervalle
    evenements: Intervalle
    part_alias: float
    part_meme_famille: float
    part_meme_nom_complet: float
    part_noms_inventes: float
    part_femmes: float
    part_adresses: float
    part_activite: float
    numero_rue: Intervalle
    roles: tuple[str, ...]
    types_evenement: tuple[str, ...]
    types_avec_montant: tuple[str, ...]
    types_avec_societe: tuple[str, ...]
    participants: Intervalle
    montants: Intervalle
    montant_centimes: Intervalle
    debut: date
    fin: date
    duree_dossier_jours: int
    corpus: dict[str, PartieCorpus]
    wikidata_url: str
    wikidata_lot: int
    wikidata_pause_s: float
    essais_max: int
    redaction: RedactionConfig
    questions: QuestionsConfig


CONFIG_CLASSES: dict[str, type[ConfigBase]] = {
    "ingest": IngestConfig,
    "search": SearchConfig,
    "model_a0": ModelConfig,
    "model_a1": ModelConfig,
    "model_b_s": ModelConfig,
    "model_b_m": ModelConfig,
    "pretrain": PretrainConfig,
    "finetune": FinetuneConfig,
    "worldgen": WorldgenConfig,
}


def load_config(name: str, configs_dir: Path = CONFIGS_DIR) -> ConfigBase:
    """Lit `configs_dir/<name>.yaml` et le valide avec la classe de `CONFIG_CLASSES`."""
    cls = CONFIG_CLASSES[name]
    with (configs_dir / f"{name}.yaml").open(encoding="utf-8") as f:
        return cls.model_validate(yaml.safe_load(f))
