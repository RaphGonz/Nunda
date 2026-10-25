"""Contrats de données (SPEC.md §4), source unique.

Deux structures : le stock SQLite (texte original, avec les noms) et l'exemple de
modèle JSON (aucun nom). Les autres modules importent ces définitions.
"""

import re
import sqlite3
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --- Énumérations ----------------------------------------------------------------


class TypePiece(StrEnum):
    PV_AUDITION = "PV_AUDITION"
    PV_CONSTATATION = "PV_CONSTATATION"
    RAPPORT = "RAPPORT"
    COURRIER = "COURRIER"
    CONTRAT = "CONTRAT"
    RELEVE = "RELEVE"
    LOI = "LOI"
    AUTRE = "AUTRE"


class GenreProposition(StrEnum):
    PHRASE = "PHRASE"
    LIGNE_TABLEAU = "LIGNE_TABLEAU"
    CHAMP = "CHAMP"
    EN_TETE = "EN_TETE"
    PARTIE = "PARTIE"


class TypeNom(StrEnum):
    """Ordre = priorité de l'union des détecteurs (SPEC.md §6)."""

    REF = "REF"
    PER = "PER"
    ORG = "ORG"
    LIEU = "LIEU"
    AUTRE = "AUTRE"


class Detecteur(StrEnum):
    GLINER = "gliner"
    SPACY = "spacy"
    REGLE = "regle"
    MAJUSCULES = "majuscules"
    PROPAGATION = "propagation"


class GenreNombre(StrEnum):
    NUM = "NUM"
    DATE = "DATE"


class PrecisionDate(StrEnum):
    JOUR = "JOUR"
    MOIS = "MOIS"
    ANNEE = "ANNEE"


class TypeArete(StrEnum):
    SUIVANTE = "SUIVANTE"
    DEPEND_DE = "DEPEND_DE"
    CONFLIT = "CONFLIT"
    DOUBLON_DE = "DOUBLON_DE"
    SECTION_DE = "SECTION_DE"


class GenreContrainte(StrEnum):
    MEME = "MEME"
    DIFFERENT = "DIFFERENT"
    IGNORER_SOURCE = "IGNORER_SOURCE"


class Relation(StrEnum):
    """Les 24 relations (SPEC.md §6). Une relation orientée a deux identifiants."""

    MEME_CHAINE = "MEME_CHAINE"
    MEME_FAMILLE = "MEME_FAMILLE"
    INITIALES_DE = "INITIALES_DE"
    PROCHE = "PROCHE"
    INCOMPATIBLE = "INCOMPATIBLE"
    SIGLE_DE = "SIGLE_DE"
    INCLUS_DANS = "INCLUS_DANS"
    ALIAS_DECLARE = "ALIAS_DECLARE"
    MEME_UTILISATEUR = "MEME_UTILISATEUR"
    DIFFERENT_UTILISATEUR = "DIFFERENT_UTILISATEUR"
    MEME_HYPOTHESE = "MEME_HYPOTHESE"
    MEME_NOMBRE = "MEME_NOMBRE"
    MEME_PROPOSITION = "MEME_PROPOSITION"
    SUIVANTE = "SUIVANTE"
    DEPEND_DE = "DEPEND_DE"
    CONFLIT = "CONFLIT"
    DOUBLON_DE = "DOUBLON_DE"
    MEME_PIECE = "MEME_PIECE"
    MEME_SECTION = "MEME_SECTION"


# Identifiants : (sens direct,) ou (sens direct, sens inverse).
RELATION_IDS: dict[Relation, tuple[int, ...]] = {
    Relation.MEME_CHAINE: (1,),
    Relation.MEME_FAMILLE: (2,),
    Relation.INITIALES_DE: (3, 4),
    Relation.PROCHE: (5,),
    Relation.INCOMPATIBLE: (6,),
    Relation.SIGLE_DE: (7, 8),
    Relation.INCLUS_DANS: (9, 10),
    Relation.ALIAS_DECLARE: (11,),
    Relation.MEME_UTILISATEUR: (12,),
    Relation.DIFFERENT_UTILISATEUR: (13,),
    Relation.MEME_HYPOTHESE: (14,),
    Relation.MEME_NOMBRE: (15,),
    Relation.MEME_PROPOSITION: (16,),
    Relation.SUIVANTE: (17, 18),
    Relation.DEPEND_DE: (19, 20),
    Relation.CONFLIT: (21,),
    Relation.DOUBLON_DE: (22,),
    Relation.MEME_PIECE: (23,),
    Relation.MEME_SECTION: (24,),
}
RELATIONS_NOMS = frozenset(r for r, ids in RELATION_IDS.items() if ids[0] <= 14)
RELATIONS_PROPS = frozenset(r for r, ids in RELATION_IDS.items() if ids[0] >= 16)

# Lexique de sortie : 25 jetons (SPEC.md §10).
LEXIQUE: tuple[str, ...] = (
    "FIN", "ABSTENTION",
    "ET", "MAIS", "DONC", "EN_REVANCHE", "PAR_AILLEURS",
    "CALCUL", "FIN_CALCUL", "+", "−", "×", "÷", "MIN", "MAX",
    "CONFLIT", "FIN_CONFLIT", "DECLARATION",
    "SAME", "SANS_PREUVE", "NOTE_SAME", "NOTE_DIFF", "ASK_SAME",
    "OUVRIR", "RETOUR",
)  # fmt: skip

# --- Stock et graphe (SQLite) -----------------------------------------------------

SQL_STOCK = """
CREATE TABLE piece (
  piece_id TEXT PRIMARY KEY, chemin TEXT, sha256 TEXT, type TEXT,
  rang INTEGER, nb_pages INTEGER, revision INTEGER);
CREATE TABLE proposition (
  prop_id INTEGER PRIMARY KEY, piece_id TEXT, page INTEGER, ordre INTEGER,
  texte TEXT, genre TEXT, ocr_conf REAL, signature TEXT, groupe_doublon INTEGER);
CREATE TABLE mention (
  mention_id INTEGER PRIMARY KEY, prop_id INTEGER, debut INTEGER, fin INTEGER,
  surface TEXT, norme TEXT, type TEXT, detecteurs TEXT);
CREATE TABLE nombre (
  nombre_id INTEGER PRIMARY KEY, prop_id INTEGER, debut INTEGER, fin INTEGER, surface TEXT,
  genre TEXT, valeur TEXT, unite TEXT, precision_date TEXT);
CREATE TABLE arete (
  src INTEGER, dst INTEGER, type TEXT,
  PRIMARY KEY (src, dst, type));
CREATE TABLE contrainte (
  conv_id TEXT, genre TEXT,
  a_norme TEXT, b_norme TEXT, piece_id TEXT, auteur TEXT, date TEXT);
CREATE TABLE trace (
  reponse_id TEXT PRIMARY KEY, conv_id TEXT, question TEXT, prop_ids TEXT, chemin_recherche TEXT,
  contraintes TEXT, actions TEXT, revision_base INTEGER, modele TEXT, date TEXT);
"""


def ouvrir_stock(chemin: Path | str) -> sqlite3.Connection:
    """Ouvre une base de dossiers ; crée les tables si la base est neuve."""
    con = sqlite3.connect(chemin)
    con.execute("PRAGMA secure_delete = ON")
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name = 'piece'").fetchone():
        con.executescript(SQL_STOCK)
    return con


# --- Exemple de modèle (JSON) -----------------------------------------------------

_MARQUEUR = re.compile(r"⟦(\d+)⟧")
_POINTEUR = re.compile(r"(?:P:(\d+)|[MN]:(\d+|q|h[1-3])\.(\d+))")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MarqueNom(_Strict):
    genre: Literal["NOM"]
    type: TypeNom
    nom: int = Field(ge=0)


class MarqueNombre(_Strict):
    genre: Literal["NUM", "DATE"]
    unite: str
    grandeur: int | None
    rang_valeur: int = Field(ge=0)
    valeur_id: int = Field(ge=0)
    signe: Literal[-1, 0, 1] | None = None  # NUM seulement (SPEC.md §6)
    precision: PrecisionDate | None = None  # DATE seulement (SPEC.md §6)

    @model_validator(mode="after")
    def _par_genre(self):
        if (self.signe is None) != (self.genre == "DATE"):
            raise ValueError("`signe` est obligatoire pour NUM et interdit pour DATE")
        if (self.precision is None) != (self.genre == "NUM"):
            raise ValueError("`precision` est obligatoire pour DATE et interdite pour NUM")
        return self


Marque = Annotated[MarqueNom | MarqueNombre, Field(discriminator="genre")]


class TexteMarque(_Strict):
    """Texte avec un marqueur ⟦i⟧ par marque, i = 0, 1, … dans l'ordre."""

    texte: str
    marques: list[Marque]

    @model_validator(mode="after")
    def _marqueurs(self):
        vus = [int(m) for m in _MARQUEUR.findall(self.texte)]
        if vus != list(range(len(self.marques))):
            raise ValueError(f"marqueurs {vus} pour {len(self.marques)} marques")
        return self


class Proposition(TexteMarque):
    local: int = Field(ge=0)
    prop_id: int
    piece: int = Field(ge=0)
    type_piece: TypePiece
    rang: int = Field(ge=0, le=4)
    ocr_bas: bool
    citee_avant: bool


class Exemple(_Strict):
    id: str
    origine: str
    langue: Literal["fr", "en"]
    question: TexteMarque
    historique: list[TexteMarque] = Field(max_length=3)
    propositions: list[Proposition] = Field(max_length=150)
    relations_noms: list[tuple[int, int, Relation]]
    relations_props: list[tuple[int, int, Relation]]
    cible: list[str] = Field(max_length=96)
    justificatives: list[int]

    @model_validator(mode="after")
    def _coherence(self):
        locaux = [p.local for p in self.propositions]
        if locaux != list(range(len(locaux))):
            raise ValueError("propositions : `local` doit valoir 0, 1, … dans l'ordre")
        for _, _, r in self.relations_noms:
            if r not in RELATIONS_NOMS:
                raise ValueError(f"{r} n'est pas une relation entre noms")
        for a, b, r in self.relations_props:
            if r not in RELATIONS_PROPS:
                raise ValueError(f"{r} n'est pas une relation entre propositions")
            if not {a, b} <= set(locaux):
                raise ValueError(f"relation {r} vers une proposition absente : ({a}, {b})")
        if not set(self.justificatives) <= set(locaux):
            raise ValueError("justificative hors des propositions")
        for pas in self.cible:
            if pas in LEXIQUE:
                continue
            m = _POINTEUR.fullmatch(pas)
            if not m:
                raise ValueError(f"pas de cible inconnu : {pas!r}")
            if m.group(1) is not None and int(m.group(1)) not in locaux:
                raise ValueError(f"pointeur vers une proposition absente : {pas!r}")
        return self
