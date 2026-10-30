"""Entrée du modèle (SPEC.md §8) : séquence de jetons et tables d'indices d'un exemple.

`encode` est la seule entrée du modèle. Le tokenizer (`decouper`) reçoit le texte entre les
marqueurs ; les jetons nouveaux (`Vocabulaire`) suivent les siens et ont leur propre table
de vecteurs. Les pas de sortie sont dans la séquence : un pointeur y reçoit le jeton de son
genre et les indices de sa cible (la position pointée).

Attributs d'un nombre (`num_attr`, §6) : 0 si absent, sinon unité (1 à `unites_max`, puis
« autre », puis JOUR, MOIS, ANNEE pour une date), ordre de grandeur (1 pour zéro, puis la
borne basse à 2), rang + 1, signe + 2.

Les noms reçoivent un numéro local 1 à N par première apparition (historique, question,
propositions), les valeurs aussi. NN[i, j] est le masque de bits des relations 1 à 14 du
nom i vers le nom j (bit id − 1) ; PP de même pour les relations 16 à 24 entre
propositions. La ligne et la colonne 0 sont vides. Une relation orientée (a, b, R) met
son premier identifiant en NN[a, b] et le second en NN[b, a].
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from ccm.anonymize.table import ORDRE_TYPES
from ccm.config import GrammarConfig, IngestConfig, ModelConfig
from ccm.grammar.automaton import Contexte, masques
from ccm.grammar.lexicon import LEXIQUE_COMPLET
from ccm.schema import (
    _MARQUEUR,
    RELATION_IDS,
    RELATIONS_NOMS,
    Exemple,
    MarqueNom,
    MarqueNombre,
    PrecisionDate,
    Relation,
    TexteMarque,
    TypePiece,
)


def ordre_apparition(ex: Exemple) -> tuple[dict[int, int], dict[int, int]]:
    """Indice `nom` → numéro local, `valeur_id` → numéro local (1, 2, …)."""
    noms: dict[int, int] = {}
    vals: dict[int, int] = {}
    for t in (*ex.historique, ex.question, *ex.propositions):
        for m in t.marques:
            if m.genre == "NOM":
                noms.setdefault(m.nom, len(noms) + 1)
            else:
                vals.setdefault(m.valeur_id, len(vals) + 1)
    return noms, vals


def _bit(r: Relation, sens: int) -> int:
    return 1 << (RELATION_IDS[r][sens] - 1)


def _poser(t: np.ndarray, a: int, b: int, r: Relation) -> None:
    t[a, b] |= _bit(r, 0)
    t[b, a] |= _bit(r, -1)


def tables_relations(ex: Exemple) -> tuple[np.ndarray, np.ndarray]:
    noms, _ = ordre_apparition(ex)
    nn = np.zeros((len(noms) + 1, len(noms) + 1), dtype=np.int64)
    for k in noms.values():
        nn[k, k] |= _bit(Relation.MEME_CHAINE, 0)
    for a, b, r in ex.relations_noms:
        _poser(nn, noms[a], noms[b], r)

    p = len(ex.propositions)
    pp = np.zeros((p + 1, p + 1), dtype=np.int64)
    for x in ex.propositions:
        pp[x.local + 1, x.local + 1] |= _bit(Relation.MEME_PROPOSITION, 0)
        for y in ex.propositions:
            if x.piece == y.piece:
                pp[x.local + 1, y.local + 1] |= _bit(Relation.MEME_PIECE, 0)
    for a, b, r in ex.relations_props:
        _poser(pp, a + 1, b + 1, r)
    return nn, pp


# --- Jetons spéciaux ------------------------------------------------------------------


def _jetons(cfg: ModelConfig, k: int) -> list[str]:
    jetons = ["[BOS]", "[H]", "[/H]", "[Q]", "[/Q]", "[P]", "[/P]", "[SORTIE]", "[MASK]",
              "[NOUVEAU]"]  # fmt: skip
    if cfg.variante == "B":
        jetons += [f"⟨{t}⟩" for t in (*ORDRE_TYPES, "NUM", "DATE")]
    else:
        jetons += [f"⟨{t}_{i}⟩" for t in (*ORDRE_TYPES, "NUM", "DATE") for i in range(k)]
    jetons += [f"⟨PIECE:{t}⟩" for t in TypePiece]
    jetons += [f"⟨RANG:{r}⟩" for r in range(5)]
    jetons += ["[OCR_BAS]", "[CITEE_AVANT]", "[CONFLIT]", "[DEPEND]"]
    if cfg.variante == "A0":
        rels = sorted(RELATIONS_NOMS - {Relation.MEME_CHAINE}, key=RELATION_IDS.__getitem__)
        jetons += ["[REL]", "[/REL]", *(f"⟨R:{r}⟩" for r in rels)]
    jetons += ["⟨PT:P⟩", "⟨PT:N⟩", "⟨PT:M⟩"]  # vecteur du genre d'un pointeur (§9)
    return [*jetons, *LEXIQUE_COMPLET]


class Vocabulaire:
    """Jetons nouveaux d'une variante ; leurs identifiants suivent les `taille` du tokenizer."""

    def __init__(self, cfg: ModelConfig, icfg: IngestConfig, taille: int):
        a = icfg.anonymiseur
        self.cfg, self.taille, self.k, self.grandeur_min = cfg, taille, a.reservoir, a.grandeur[0]
        self.jetons = _jetons(cfg, a.reservoir)
        self.ids = {j: taille + i for i, j in enumerate(self.jetons)}
        unites = [u.unite for u in icfg.nombres.unites] + [icfg.nombres.unite_heure_du_jour]
        self.unites = {u: i for i, u in enumerate(unites, 1)}
        self.autre = a.unites_max + 1
        if len(self.unites) > a.unites_max:
            raise ValueError(f"{len(self.unites)} unités pour {a.unites_max} cases")

    def slot(self, m: MarqueNom | MarqueNombre) -> int:
        nom = isinstance(m, MarqueNom)
        famille = m.type if nom else m.genre
        if self.cfg.variante == "B":
            return self.ids[f"⟨{famille}⟩"]
        return self.ids[f"⟨{famille}_{m.nom % self.k if nom else m.valeur_id}⟩"]

    def attributs(self, m: MarqueNombre) -> tuple[int, int, int, int]:
        if m.genre == "DATE":
            return self.autre + 1 + list(PrecisionDate).index(m.precision), 0, m.rang_valeur + 1, 0
        grandeur = 1 if m.grandeur is None else m.grandeur - self.grandeur_min + 2
        return self.unites.get(m.unite, self.autre), grandeur, m.rang_valeur + 1, m.signe + 2


# --- Encodage -------------------------------------------------------------------------


@dataclass(frozen=True)
class Encodage:
    """Tables de §8. `espace` : pas de la tête de sortie, lexique (L), propositions (P),
    nombres (K), mentions (M) ; `cible` et `masque` s'y lisent. `prop_nombre` : proposition
    de chaque nombre (1 à P). `masque` : None sans contexte de grammaire."""

    input_ids: np.ndarray
    segment: np.ndarray
    prop_idx: np.ndarray
    name_idx: np.ndarray
    val_idx: np.ndarray
    num_attr: np.ndarray
    NN: np.ndarray
    PP: np.ndarray
    fin_prop: np.ndarray
    pos_mention: np.ndarray
    pos_nombre: np.ndarray
    prop_nombre: np.ndarray
    cible: np.ndarray
    masque: np.ndarray | None
    espace: tuple[str, ...]


def masque_pas(espace: Sequence[str], permis: frozenset[str]) -> np.ndarray:
    """Pas permis par l'automate → vecteur de l'espace des pas."""
    m = np.fromiter((p in permis for p in espace), dtype=bool, count=len(espace))
    if m.sum() != len(permis):
        raise ValueError(f"pas hors de l'espace : {sorted(permis - set(espace))}")
    return m


def encode(
    ex: Exemple,
    voc: Vocabulaire,
    decouper: Callable[[str], Sequence[int]],
    *,
    ctx: Contexte | None = None,
    gcfg: GrammarConfig | None = None,
) -> Encodage:
    """Exemple → séquence et tables (§8). Variante et limites : `voc.cfg`. `decouper` :
    texte → jetons, sans jeton spécial. Avec `ctx` et `gcfg`, le masque de chaque pas de
    `ex.cible` (erreur si un pas est interdit). Sans cible, la séquence finit à [SORTIE]."""
    cfg, ids = voc.cfg, voc.ids
    if len(ex.propositions) > cfg.p_max:
        raise ValueError(f"P = {len(ex.propositions)} > {cfg.p_max} ({ex.id})")
    if len(ex.cible) > cfg.s_max:
        raise ValueError(f"S = {len(ex.cible)} > {cfg.s_max} ({ex.id})")
    noms, vals = ordre_apparition(ex)
    lignes: list[tuple] = []  # jeton, segment, prop_idx, name_idx, val_idx, num_attr
    segment = 0
    mentions: dict[str, int] = {}
    nombres: dict[str, int] = {}

    def ajouter(jeton: int, prop=0, nom=0, val=0, attr=(0, 0, 0, 0)) -> int:
        lignes.append((jeton, segment, prop, nom, val, attr))
        return len(lignes) - 1

    def texte(tm: TexteMarque, t: str, prop: int = 0) -> None:
        for i, morceau in enumerate(_MARQUEUR.split(tm.texte)):
            if i % 2 == 0:
                for jeton in decouper(morceau) if morceau else ():
                    ajouter(jeton, prop)
                continue
            j = int(morceau)
            m = tm.marques[j]
            if isinstance(m, MarqueNom):
                mentions[f"M:{t}.{j}"] = ajouter(voc.slot(m), prop, nom=noms[m.nom])
            else:
                pos = ajouter(voc.slot(m), prop, val=vals[m.valeur_id], attr=voc.attributs(m))
                if prop:  # seuls les nombres des propositions sont pointables (§10)
                    nombres[f"N:{t}.{j}"] = pos

    # Historique et question.
    ajouter(ids["[BOS]"])
    for i, h in enumerate(ex.historique):
        ajouter(ids["[H]"])
        texte(h, f"h{len(ex.historique) - i}")
        ajouter(ids["[/H]"])
    ajouter(ids["[Q]"])
    texte(ex.question, "q")
    ajouter(ids["[/Q]"])

    # Contexte.
    segment = 1
    if cfg.variante == "A0":
        # Coupe par ordre d'apparition : indépendante des indices tirés au hasard.
        rels = sorted(ex.relations_noms, key=lambda x: (noms[x[0]], noms[x[1]], RELATION_IDS[x[2]]))
        marques = {m.nom: m for t in (*ex.historique, ex.question, *ex.propositions)
                   for m in t.marques if isinstance(m, MarqueNom)}  # fmt: skip
        ajouter(ids["[REL]"])
        for a, b, r in rels[: cfg.rel_max]:
            ajouter(voc.slot(marques[a]), nom=noms[a])
            ajouter(ids[f"⟨R:{r}⟩"])
            ajouter(voc.slot(marques[b]), nom=noms[b])
        ajouter(ids["[/REL]"])
    conflit = {x for a, b, r in ex.relations_props if r == Relation.CONFLIT for x in (a, b)}
    depend = {a for a, _, r in ex.relations_props if r == Relation.DEPEND_DE}
    fins = []
    for p in ex.propositions:
        k = p.local + 1
        ajouter(ids["[P]"], k)
        ajouter(ids[f"⟨PIECE:{p.type_piece}⟩"], k)
        ajouter(ids[f"⟨RANG:{p.rang}⟩"], k)
        for present, jeton in (
            (p.ocr_bas, "[OCR_BAS]"),
            (p.citee_avant, "[CITEE_AVANT]"),
            (p.local in conflit, "[CONFLIT]"),
            (p.local in depend, "[DEPEND]"),
        ):
            if present:
                ajouter(ids[jeton], k)
        texte(p, str(p.local), k)
        fins.append(ajouter(ids["[/P]"], k))

    # Sortie : un pointeur hérite des indices de sa cible.
    segment = 2
    ajouter(ids["[SORTIE]"])
    cibles = {f"P:{k}": pos for k, pos in enumerate(fins)} | nombres | mentions
    for pas in ex.cible:
        if pas in cibles:
            _, _, prop, nom, val, attr = lignes[cibles[pas]]
            ajouter(ids[f"⟨PT:{pas[0]}⟩"], prop, nom, val, attr)
        else:
            ajouter(ids[pas])
    if len(lignes) > cfg.t_max:
        raise ValueError(f"T = {len(lignes)} > {cfg.t_max} ({ex.id})")

    espace = (*LEXIQUE_COMPLET, *cibles)
    indice = {p: i for i, p in enumerate(espace)}
    masque = None
    if ctx is not None:
        masque = np.zeros((len(ex.cible), len(espace)), dtype=bool)
        for t, permis in enumerate(masques(ctx, ex.cible, gcfg)):
            masque[t] = masque_pas(espace, permis)
    colonnes = [np.array(c, dtype=np.int64) for c in zip(*lignes, strict=True)]
    nn, pp = tables_relations(ex)
    pos_nombre = np.array(list(nombres.values()), dtype=np.int64)
    return Encodage(
        input_ids=colonnes[0],
        segment=colonnes[1],
        prop_idx=colonnes[2],
        name_idx=colonnes[3],
        val_idx=colonnes[4],
        num_attr=colonnes[5],
        NN=nn,
        PP=pp,
        fin_prop=np.array(fins, dtype=np.int64),
        pos_mention=np.array(list(mentions.values()), dtype=np.int64),
        pos_nombre=pos_nombre,
        prop_nombre=colonnes[2][pos_nombre],
        cible=np.array([indice[p] for p in ex.cible], dtype=np.int64),
        masque=masque,
        espace=espace,
    )
