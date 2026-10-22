"""Relations entre noms (SPEC.md §6, relations 1 à 14).

Le code lit les chaînes ; il ne décide jamais que deux noms désignent la même personne.
Un nom est une norme et un type ; il peut avoir plusieurs surfaces (« DUPONT Jean »,
« Dupont Jean »). Une relation vaut si elle vaut pour au moins un couple de surfaces.
Une relation orientée (a, b, R) se lit « a R b » ; une relation symétrique est rendue une
fois, plus petit indice d'abord. MEME_CHAINE (même norme, même type) est le nom lui-même :
elle est sur la diagonale de la table NN (`encode.py`), pas dans la liste.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property
from itertools import pairwise

from rapidfuzz.distance import DamerauLevenshtein

from ccm.anonymize.names import _INITIALES, AnalyseNom, analyser, norme
from ccm.config import IngestConfig, NomsConfig
from ccm.ingest.racines import sans_accents
from ccm.schema import RELATION_IDS, Relation, TypeNom

SYMETRIQUES = frozenset(r for r, ids in RELATION_IDS.items() if len(ids) == 1)
_SIGLE = re.compile(r"[A-Z]{2,8}")
_SEPARATEUR = re.compile(r"[-‐–\s]+")


@dataclass(frozen=True)
class Nom:
    norme: str
    type: TypeNom
    surfaces: frozenset[str]
    genres: frozenset[str] = frozenset()  # genres des titres placés devant ses mentions


@dataclass
class _Lu:
    """Ce que les règles lisent d'un nom."""

    nom: Nom
    cfg: IngestConfig
    mots: frozenset[str] = field(init=False)

    def __post_init__(self):
        self.mots = frozenset(self.nom.norme.split())

    @cached_property
    def analyses(self) -> list[AnalyseNom]:
        if self.nom.type != TypeNom.PER:
            return []
        return [analyser(s, self.cfg.noms) for s in sorted(self.nom.surfaces)]

    @cached_property
    def familles(self) -> set[str]:
        return {a.famille for a in self.analyses if a.famille}

    @cached_property
    def initiales(self) -> set[str]:
        """Jeux d'initiales écrits (« J.-P. » → « JP »), quel que soit le type."""
        return {
            re.sub(r"[.-]", "", s) for s in self.nom.surfaces if _INITIALES.fullmatch(s.strip())
        }

    @cached_property
    def initiales_possibles(self) -> set[str]:
        """Initiales des prénoms, et des prénoms et du nom (mots pleins), d'un nom PER."""
        out = set()
        for a in self.analyses:
            if a.prenoms and a.famille:
                p = "".join(x[0] for x in a.prenoms).upper()
                f = [m for m in a.famille.split() if m not in self.cfg.noms.particules]
                out |= {p, p + "".join(m[0] for m in f).upper()}
        return out

    @cached_property
    def sigles(self) -> set[str]:
        out = set()
        for s in self.nom.surfaces:
            x = sans_accents(s.strip()).replace(".", "")
            if _SIGLE.fullmatch(x):
                out.add(x)
        return out

    @cached_property
    def initiales_mots_pleins(self) -> set[str]:
        """Initiales des mots pleins : un mot vide est en minuscules et dans la liste des mots
        vides ou des particules."""
        vides = set(self.cfg.racines.mots_vides) | set(self.cfg.noms.particules)
        out = set()
        for s in self.nom.surfaces:
            mots = [m for m in _SEPARATEUR.split(s.strip()) if m]
            pleins = [m for m in mots if not (m.islower() and norme(m, self.cfg.noms) in vides)]
            if len(pleins) >= 2:
                out.add("".join(sans_accents(m[0]).upper() for m in pleins))
        return out


def _prenoms_compatibles(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Égaux, préfixe (« jean » / « jean pierre ») ou initiales (« j p » / « jean pierre »)."""
    if not a or not b:
        return True
    return all(
        x == y or (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y))
        for x, y in zip(a, b, strict=False)  # préfixe : le plus court
    )


def _proche(a: str, b: str) -> bool:
    n = min(len(a), len(b))
    d = DamerauLevenshtein.distance(a, b, score_cutoff=2)
    return (d == 1 and n >= 5) or (d == 2 and n >= 10)


def _orientees(a: _Lu, b: _Lu) -> Iterable[Relation]:
    """Relations orientées « a R b »."""
    if a.initiales & b.initiales_possibles:
        yield Relation.INITIALES_DE
    if a.sigles & b.initiales_mots_pleins:
        yield Relation.SIGLE_DE
    if a.mots < b.mots:
        yield Relation.INCLUS_DANS


def _symetriques(a: _Lu, b: _Lu) -> Iterable[Relation]:
    if a.familles & b.familles:
        yield Relation.MEME_FAMILLE
        if _incompatibles(a, b):
            yield Relation.INCOMPATIBLE
    if _proche(a.nom.norme, b.nom.norme):
        yield Relation.PROCHE


def _incompatibles(a: _Lu, b: _Lu) -> bool:
    if any(ga != gb for ga in a.nom.genres for gb in b.nom.genres):
        return True
    return any(
        x.famille == y.famille and not _prenoms_compatibles(x.prenoms, y.prenoms)
        for x in a.analyses
        for y in b.analyses
        if x.famille
    )


def _orienter(a: int, b: int, r: Relation) -> tuple[int, int, Relation]:
    return (min(a, b), max(a, b), r) if r in SYMETRIQUES else (a, b, r)


def relations_noms(
    noms: list[Nom],
    cfg: IngestConfig,
    declarees: Iterable[tuple[int, int, Relation]] = (),
) -> set[tuple[int, int, Relation]]:
    """Relations 2 à 11 calculées entre les noms, plus les relations déclarées (ALIAS_DECLARE,
    MEME_UTILISATEUR, DIFFERENT_UTILISATEUR, MEME_HYPOTHESE). Indices : rangs dans `noms`."""
    lus = [_Lu(n, cfg) for n in noms]
    out = set()
    for i, a in enumerate(lus):
        for j in range(i + 1, len(lus)):
            b = lus[j]
            out |= {(i, j, r) for r in _orientees(a, b)}
            out |= {(j, i, r) for r in _orientees(b, a)}
            out |= {(i, j, r) for r in _symetriques(a, b)}
    out |= {_orienter(a, b, r) for a, b, r in declarees if a != b}
    return out


def alias_declares(
    texte: str, mentions: list[tuple[int, int, int]], cfg: NomsConfig
) -> set[tuple[int, int]]:
    """ALIAS_DECLARE (relation 11) : deux mentions voisines d'une proposition reliées par
    un motif (« A, dit B »). `mentions` : (début, fin, indice du nom)."""
    motifs = [re.compile(m) for m in cfg.alias]
    ms = sorted(mentions)
    out = set()
    for (_, fa, a), (db, _, b) in pairwise(ms):
        if a != b and any(m.fullmatch(texte[fa:db]) for m in motifs):
            out.add((min(a, b), max(a, b)))
    return out


def genre_titre(texte: str, debut: int, cfg: NomsConfig) -> str | None:
    """Genre du titre écrit juste devant une mention (« M. », « Mme »), sinon None."""
    m = re.search(r"(\S+)\s+$", texte[:debut])
    return cfg.genres.get(norme(m.group(1), cfg).rstrip(".")) if m else None
