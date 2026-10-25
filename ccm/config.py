"""Lecture des configurations YAML, validées par pydantic (SPEC.md §3).

Chaque fichier de `configs/` a sa classe. Les champs s'ajoutent phase par phase ;
une clé inconnue est une erreur.
"""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from ccm.schema import Relation, TypeNom, TypePiece

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


class ConfigBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    description: str


class _Bloc(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TableauxConfig(_Bloc):
    """Étape 4 (SPEC.md §5) : cellules tracées. Distances en points."""

    cote_min: float  # largeur et hauteur minimales d'une cellule (un filet n'en est pas une)
    tolerance: float  # écart d'ordonnée admis entre les cellules d'une rangée
    cellules_min: int


class ExtractionConfig(_Bloc):
    """Étape 1 (SPEC.md §5). Distances en points."""

    tableaux: TableauxConfig
    ocr_caracteres_min: int
    ocr_dpi: int
    ocr_langue: str
    tesseract: tuple[str, ...]  # exécutables essayés dans l'ordre
    tessdata: str  # dossier des modèles, relatif à la racine du dépôt (ignoré s'il manque)
    gouttiere_min: float
    largeur_min_colonne: float
    ecart_bloc: float  # × hauteur médiane des mots
    facteur_paragraphe: float  # × hauteur médiane des lignes (texte natif)
    facteur_paragraphe_ocr: float


class MotifPiece(_Bloc):
    motif: str  # expression régulière, sensible à la casse
    type: TypePiece


class PiecesConfig(_Bloc):
    """Étape 2 (SPEC.md §5)."""

    lignes_en_tete: int
    motifs: tuple[MotifPiece, ...]  # le premier trouvé donne le type
    rang: dict[TypePiece, int]  # type absent : 0 (non classé)


class SegmentationConfig(_Bloc):
    """Étapes 3 et 3 bis (SPEC.md §5)."""

    dependance_mots: tuple[str, ...]
    mots_min: int
    motif_question: str
    motif_reponse: str
    abreviations: tuple[str, ...]  # sans le point final
    mots_max: int
    motif_champ: str  # étape 4 : paragraphe « Libellé : valeur »


class UniteConfig(_Bloc):
    unite: str
    formes: tuple[str, ...]  # expressions régulières, après le nombre


class NombresConfig(_Bloc):
    """Étape 6 (SPEC.md §5)."""

    references: tuple[str, ...]  # expressions régulières ; jamais des nombres
    mois: tuple[str, ...]  # janvier … décembre
    annee_min: int
    annee_max: int
    unites: tuple[UniteConfig, ...]  # la première forme trouvée l'emporte
    unite_heure_du_jour: str
    avant_heure_du_jour: tuple[str, ...]  # « à 21 heures » : heure du jour, pas durée
    lettres: dict[str, int]  # nombres en lettres ; 100 et plus : multiplicateurs


class DoublonsConfig(_Bloc):
    """Étape 7 (SPEC.md §5)."""

    permutations: int
    seuil_jaccard: float
    mots_par_triplet: int
    graine: int


class RacinesConfig(_Bloc):
    """Racines des mots : types d'acte des conflits (SPEC.md §5) et index BM25 (§7)."""

    langue: str  # langue Snowball
    mots_vides: tuple[str, ...]


class NomsConfig(_Bloc):
    """Norme d'un nom (SPEC.md §6)."""

    titres: tuple[str, ...]  # retirés en tête, comparés après normalisation
    particules: tuple[str, ...]  # du nom de famille, après normalisation
    genres: dict[str, Literal["M", "F"]]  # titre normalisé → genre (INCOMPATIBLE)
    alias: tuple[str, ...]  # ALIAS_DECLARE : expressions régulières du texte entre deux noms


class AnonymiseurConfig(_Bloc):
    """Slots et attributs (SPEC.md §6)."""

    reservoir: int  # K
    grandeur: tuple[int, int]
    rang_max: int
    ocr_bas: float


class ConflitsConfig(_Bloc):
    """Étape 8 (SPEC.md §5) : conflits établis."""

    negation: tuple[str, ...]  # expressions régulières, sans casse
    unite_euro: str
    actes: dict[str, tuple[str, ...]]  # type d'acte → mots, comparés par racine
    motif_article: str  # groupe 1 : numéro de l'article
    motif_code: str


class GlinerConfig(_Bloc):
    modele: str  # dossier, relatif à la racine du dépôt
    seuil: float
    lot: int
    appareil: str  # auto, cuda ou cpu
    etiquettes: dict[str, TypeNom]  # étiquette demandée → type


class SpacyConfig(_Bloc):
    modele: str  # paquet installé
    etiquettes: dict[str, TypeNom]  # étiquette de spaCy → type ; les autres sont ignorées


class DetectionConfig(_Bloc):
    """Étape 5 (SPEC.md §6) : union des détecteurs D1 à D4."""

    detecteurs: tuple[Literal["gliner", "spacy", "regle", "majuscules"], ...]
    gliner: GlinerConfig
    spacy: SpacyConfig
    regles: tuple[str, ...]  # D3, en plus de `nombres.references`
    lexiques: tuple[str, ...]  # D4 : dictionnaires Hunspell, sans extension
    elisions: tuple[str, ...]  # retirées en tête d'un mot (« qu'Elodie »)
    propagation_min: int  # longueur minimale d'une chaîne propagée


class IngestConfig(ConfigBase):
    extraction: ExtractionConfig
    pieces: PiecesConfig
    segmentation: SegmentationConfig
    nombres: NombresConfig
    doublons: DoublonsConfig
    racines: RacinesConfig
    noms: NomsConfig
    detection: DetectionConfig
    conflits: ConflitsConfig
    anonymiseur: AnonymiseurConfig


class Bm25Config(_Bloc):
    k1: float
    b: float


class DepartsConfig(_Bloc):
    par_nom: int
    par_texte: int
    relations: list[Relation]


class ClassementConfig(_Bloc):
    poids_noms: float
    bonus_depart: float


class SecondTourConfig(_Bloc):
    meilleures: int
    noms_max: int
    tours: int


class BudgetConfig(_Bloc):
    propositions: int
    jetons: int
    jetons_a: int


class JetonsConfig(_Bloc):
    par_proposition: int
    par_mot: float


class SearchConfig(ConfigBase):
    bm25: Bm25Config
    departs: DepartsConfig
    classement: ClassementConfig
    second_tour: SecondTourConfig
    budget: BudgetConfig
    jetons: JetonsConfig


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
