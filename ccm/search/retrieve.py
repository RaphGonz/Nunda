"""Recherche (SPEC.md §7) : au plus 150 propositions et 3 500 jetons, dans un ordre fixe,
avec la raison de chaque choix.

1. Départs par noms : propositions qui contiennent un nom de la question (norme égale,
   puis noms reliés), au plus `par_nom` par nom, classées par BM25.
1 bis. Départs par texte : les `par_texte` meilleures propositions BM25 (score non nul).
2. Extension : un saut par SUIVANTE et CONFLIT, DEPEND_DE en fermeture complète (les deux
   sens des arêtes).
3. Classement : BM25 normalisé (par le meilleur score de l'index) + poids × noms de la
   question couverts + bonus si départ ; égalité : plus petit prop_id.
4. Second tour : les noms nouveaux des meilleures propositions deviennent des départs.
5. Contraintes : MEME ajoute l'autre nom aux noms de la question ; IGNORER_SOURCE retire
   les propositions de la pièce.
6. Fermeture et coupe : une proposition entre avec ses dépendances et ses conflits, si le
   tout tient dans le budget (propositions, jetons, K noms par type) ; sinon elle saute.
7. Ordre : groupes par pièce, dans l'ordre du document ; pièces par meilleur score.

Question sans nom : les noms du message précédent le plus récent qui en a. Les
propositions citées au tour précédent entrent d'abord, avec la marque `citee_avant`.
"""

import json
import sqlite3
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime

from ccm.anonymize.exemple import Message, lire_message  # noqa: F401 (commande search)
from ccm.anonymize.names import norme
from ccm.anonymize.relations import Nom
from ccm.config import IngestConfig, SearchConfig
from ccm.graph.store import revision
from ccm.search.bm25 import Index
from ccm.search.expand import Graphe, jetons


@dataclass(frozen=True)
class Raison:
    prop_id: int
    score: float
    noms: tuple[str, ...] = ()  # départ par ces noms (question ou second tour)
    texte: bool = False  # départ par texte
    sauts: tuple[str, ...] = ()  # SUIVANTE, DEPEND_DE, CONFLIT, FERMETURE
    tour: int = 0  # 0 : citée avant seulement
    citee_avant: bool = False


@dataclass(frozen=True)
class Resultat:
    prop_ids: list[int]  # ordre du contexte
    raisons: dict[int, Raison]
    noms: tuple[str, ...]  # normes cherchées : question, reprises, contraintes MEME
    jetons: int
    contraintes: list[tuple] = field(default_factory=list)


def _noms(m: Message, cfg: IngestConfig) -> list[Nom]:
    out: dict[str, Nom] = {}
    for d, f, t in m.noms:
        out.setdefault(norme(m.texte[d:f], cfg.noms), Nom(norme(m.texte[d:f], cfg.noms), t,
                                                          frozenset({m.texte[d:f]})))  # fmt: skip
    return list(out.values())


@dataclass
class _Cand:
    noms: list[str] = field(default_factory=list)
    texte: bool = False
    sauts: set[str] = field(default_factory=set)
    tour: int = 0


def chercher(
    con: sqlite3.Connection,
    index: Index,
    question: Message,
    cfg_s: SearchConfig,
    cfg: IngestConfig,
    *,
    precedentes: Sequence[Message] = (),
    conv_id: str | None = None,
    citees: frozenset[int] = frozenset(),
    jetons_max: int | None = None,
) -> Resultat:
    g = Graphe(con)
    contraintes = (
        con.execute(
            "SELECT genre, a_norme, b_norme, piece_id FROM contrainte WHERE conv_id = ? "
            "ORDER BY rowid",
            (conv_id,),
        ).fetchall()
        if conv_id is not None
        else []
    )
    ignorees = {pc for genre, _, _, pc in contraintes if genre == "IGNORER_SOURCE"}

    def permise(p: int) -> bool:
        pc = g.props[p][0]
        return not any(pc == i or pc.startswith(f"{i}.") for i in ignorees)

    # Noms de la question ; question de suite ; contraintes MEME.
    noms = _noms(question, cfg)
    for m in reversed(precedentes):
        if noms:
            break
        noms = _noms(m, cfg)
    vus = {n.norme for n in noms}
    for genre, a, b, _ in contraintes:
        for x, y in ((a, b), (b, a)):
            if genre == "MEME" and x in vus and y not in vus:
                t = next((n.type for n in g.noms if n.norme == y), noms[0].type)
                noms.append(Nom(y, t, frozenset({y})))
                vus.add(y)

    bm = index.scores(question.texte, cfg.racines)
    bm_max = max(bm.values(), default=0.0) or 1.0
    couvre: dict[str, set[str]] = {}  # norme d'un nom de la question → normes qui le couvrent
    cands: dict[int, _Cand] = {}

    def ajouter(p: int, tour: int) -> _Cand | None:
        if p not in g.props or not permise(p):
            return None
        c = cands.setdefault(p, _Cand(tour=tour))
        c.tour = min(c.tour, tour)
        return c

    def departs_nom(n: Nom, tour: int) -> list[str]:
        relies = g.relies(n, cfg_s, cfg)
        cle = lambda p: (-bm.get(p, 0.0), p)  # noqa: E731
        egaux = sorted(g.par_norme.get(n.norme, ()), key=cle)
        autres = sorted(set().union(*(g.par_norme[r] for r in relies)) - set(egaux), key=cle)
        k = 0
        for p in egaux + autres:
            if k == cfg_s.departs.par_nom:
                break
            if (c := ajouter(p, tour)) is not None:
                k += 1
                if n.norme not in c.noms:
                    c.noms.append(n.norme)
        return [n.norme, *relies]

    def etendre(departs: list[int], tour: int) -> None:
        for p in departs:
            for q, t in g.extension(p):
                if (c := ajouter(q, tour)) is not None:
                    c.sauts.add(t)

    def score(p: int) -> float:
        normes = {n for n, _ in g.mentions.get(p, ())}
        c = cands.get(p)
        return (
            bm.get(p, 0.0) / bm_max
            + cfg_s.classement.poids_noms * sum(bool(normes & s) for s in couvre.values())
            + (cfg_s.classement.bonus_depart if c and (c.noms or c.texte) else 0.0)
        )

    def classer() -> list[int]:
        return sorted(cands, key=lambda p: (-score(p), p))

    # Tour 1 : noms et texte.
    for n in noms:
        couvre[n.norme] = set(departs_nom(n, 1))
    for p, _ in sorted(bm.items(), key=lambda x: (-x[1], x[0]))[: cfg_s.departs.par_texte]:
        if (c := ajouter(p, 1)) is not None:
            c.texte = True
    etendre([p for p, c in cands.items() if c.noms or c.texte], 1)
    connus = set().union(*couvre.values()) if couvre else set()

    # Tours suivants : noms nouveaux des meilleures propositions.
    for tour in range(2, cfg_s.second_tour.tours + 1):
        nouveaux: list[Nom] = []
        for p in classer()[: cfg_s.second_tour.meilleures]:
            for nm, t in g.mentions.get(p, ()):
                if nm not in connus and len(nouveaux) < cfg_s.second_tour.noms_max:
                    connus.add(nm)
                    nouveaux.append(next(x for x in g.noms if x.norme == nm and x.type == t))
        avant = {p: (list(c.noms), c.texte) for p, c in cands.items()}
        for n in nouveaux:
            connus |= set(departs_nom(n, tour))
        etendre([p for p, c in cands.items() if (c.noms, c.texte) != avant.get(p)], tour)

    # Fermeture et coupe.
    p_max = cfg_s.budget.propositions
    j_max = cfg_s.budget.jetons if jetons_max is None else jetons_max
    choisies: set[int] = set()
    par_type: dict[str, set[str]] = defaultdict(set)
    total = 0
    fermees: set[int] = set()

    def prendre(p: int, force: bool = False) -> None:
        nonlocal total
        groupe = {q for q in g.fermeture(p) if permise(q)} - choisies
        cout = sum(jetons(g.props[q][3], cfg_s) for q in groupe)
        types = defaultdict(set, {t: set(s) for t, s in par_type.items()})
        for q in groupe:
            for nm, t in g.mentions.get(q, ()):
                types[t].add(nm)
        if not force and (
            len(choisies) + len(groupe) > p_max
            or total + cout > j_max
            or any(len(s) > cfg.anonymiseur.reservoir for s in types.values())
        ):
            return
        choisies.update(groupe)
        fermees.update(groupe - {p})
        par_type.update(types)
        total += cout

    for p in sorted(citees):
        if p in g.props and permise(p):
            prendre(p, force=True)
    for p in classer():
        if p not in choisies:
            prendre(p)

    # Ordre du contexte.
    scores = {p: score(p) for p in choisies}
    meilleur: dict[str, tuple] = {}
    for p in choisies:
        pc, k = g.props[p][0], (-scores[p], p)
        meilleur[pc] = min(meilleur.get(pc, k), k)
    ordre = sorted(choisies, key=lambda p: (meilleur[g.props[p][0]], g.props[p][1:3], p))
    raisons = {}
    for p in ordre:
        c = cands.get(p, _Cand())
        sauts = c.sauts | ({"FERMETURE"} if p in fermees and p not in cands else set())
        raisons[p] = Raison(p, round(scores[p], 6), tuple(c.noms), c.texte, tuple(sorted(sauts)),
                            c.tour, p in citees)  # fmt: skip
    return Resultat(ordre, raisons, tuple(n.norme for n in noms), total,
                    [tuple(c) for c in contraintes])  # fmt: skip


def ecrire_trace(
    con: sqlite3.Connection, res: Resultat, question: str, conv_id: str | None = None
) -> str:
    """Ligne de la table `trace` : propositions et chemin de la recherche."""
    rid = uuid.uuid4().hex
    con.execute(
        "INSERT INTO trace (reponse_id, conv_id, question, prop_ids, chemin_recherche, "
        "contraintes, revision_base, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rid,
            conv_id,
            question,
            json.dumps(res.prop_ids),
            json.dumps([asdict(res.raisons[p]) for p in res.prop_ids], ensure_ascii=False),
            json.dumps(res.contraintes, ensure_ascii=False),
            revision(con),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    return rid
