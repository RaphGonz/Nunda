"""Les quatre détecteurs de noms (SPEC.md §6), sans modèle génératif.

D1 : GLiNER multilingue (encodeur), seuil bas. D2 : spaCy `fr_core_news_lg`. D3 : règles
(références). D4 : majuscules, mot absent des lexiques de mots courants, type AUTRE.
Chaque détecteur rend des zones (début, fin, type) ; l'union est dans `ner.union`. Les
modèles sont lus sur le disque, jamais sur le réseau.
"""

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from ccm.config import DetectionConfig, GlinerConfig, NombresConfig, SpacyConfig
from ccm.schema import Detecteur, TypeNom

RACINE = Path(__file__).resolve().parent.parent.parent

_MOT = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
_INITIALES = re.compile(r"(?<!\w)(?:[A-Z]\.\s?-?){2,3}(?!\w)")  # « S.M. », « J.-P. »


@dataclass(frozen=True)
class Zone:
    debut: int
    fin: int
    type: TypeNom
    detecteurs: frozenset[Detecteur]


@cache
def _gliner(modele: str, appareil: str):
    import torch
    from gliner import GLiNER

    dossier = RACINE / modele
    encodeur = json.loads((dossier / "gliner_config.json").read_text(encoding="utf-8"))
    if not Path(encodeur["model_name"]).is_dir():
        raise FileNotFoundError(f"encodeur absent de {dossier} : lancer `ccm modeles`")
    if appareil == "auto":
        appareil = "cuda" if torch.cuda.is_available() else "cpu"
    return GLiNER.from_pretrained(str(dossier), local_files_only=True, map_location=appareil)


def d1_gliner(textes: list[str], cfg: GlinerConfig) -> list[list[Zone]]:
    pleins = [i for i, t in enumerate(textes) if t.strip()]
    sortie: list[list[Zone]] = [[] for _ in textes]
    if not pleins:
        return sortie
    res = _gliner(cfg.modele, cfg.appareil).inference(
        [textes[i] for i in pleins], list(cfg.etiquettes), threshold=cfg.seuil, batch_size=cfg.lot
    )
    d = frozenset({Detecteur.GLINER})
    for i, ents in zip(pleins, res, strict=True):
        sortie[i] = [Zone(e["start"], e["end"], cfg.etiquettes[e["label"]], d) for e in ents]
    return sortie


@cache
def _spacy(modele: str):
    import spacy

    nlp = spacy.load(modele)
    nlp.select_pipes(enable=[p for p in nlp.pipe_names if p in ("tok2vec", "ner")])
    return nlp


def d2_spacy(textes: list[str], cfg: SpacyConfig) -> list[list[Zone]]:
    d = frozenset({Detecteur.SPACY})
    return [
        [
            Zone(e.start_char, e.end_char, cfg.etiquettes[e.label_], d)
            for e in doc.ents
            if e.label_ in cfg.etiquettes
        ]
        for doc in _spacy(cfg.modele).pipe(textes)
    ]


@cache
def _regles(motifs: tuple[str, ...]) -> list[re.Pattern]:
    return [re.compile(rf"(?<!\w){m}(?!\w)") for m in motifs]


def d3_regles(texte: str, cfg: DetectionConfig, nombres: NombresConfig) -> list[Zone]:
    d = frozenset({Detecteur.REGLE})
    return [
        Zone(*m.span(), TypeNom.REF, d)
        for r in _regles(nombres.references + cfg.regles)
        for m in r.finditer(texte)
    ]


@cache
def _lexiques(chemins: tuple[str, ...]):
    from spylls.hunspell import Dictionary

    return [Dictionary.from_files(str(RACINE / c)) for c in chemins]


@cache
def _courant(mot: str, chemins: tuple[str, ...]) -> bool:
    """Mot courant : sa forme en minuscules est reconnue, ou chacune de ses parties à tiret."""
    lex = _lexiques(chemins)
    if any(d.lookup(mot.lower()) for d in lex):
        return True
    parties = mot.split("-")
    return len(parties) > 1 and all(_courant(p, chemins) for p in parties if p)


def d4_majuscules(texte: str, cfg: DetectionConfig) -> list[Zone]:
    """Mots à majuscule initiale (ou tout en majuscules) absents des lexiques, et jeux
    d'initiales ; les mots voisins séparés par des blancs forment une seule zone."""
    elision = re.compile(rf"(?:{'|'.join(cfg.elisions)})['’]", re.IGNORECASE)
    mots = [m.span() for m in _INITIALES.finditer(texte)]
    for m in _MOT.finditer(texte):
        debut, mot = m.start(), m.group()
        if e := elision.match(mot):
            debut, mot = debut + e.end(), mot[e.end() :]
        if mot and mot[0].isupper() and not _courant(mot, cfg.lexiques):
            if not any(a <= debut < b for a, b in mots):
                mots.append((debut, m.end()))
    zones: list[list[int]] = []
    for a, b in sorted(mots):
        if zones and texte[zones[-1][1] : a].strip(" \t") == "" and a >= zones[-1][1]:
            zones[-1][1] = b
        else:
            zones.append([a, b])
    d = frozenset({Detecteur.MAJUSCULES})
    return [Zone(a, b, TypeNom.AUTRE, d) for a, b in zones]
