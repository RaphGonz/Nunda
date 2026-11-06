"""Chargeur de données du réglage fin (SPEC.md §12, « Exemples négatifs et difficiles » ; §13).

Une époque est un plan fixé par la graine : chaque source reçoit sa part des exemples
(`chargeur.poids`, renormalisés sur les sources présentes), ses questions sont prises dans
un ordre tiré pour l'époque, puis les places sont mélangées. Chaque exemple est construit à
neuf, dans cet ordre :

1. Genre, tiré une fois par exemple : abstention (justificatives et doublons retirés du
   stock ; pour le corpus synthétique, aussi toutes les lignes de leurs événements, d'après
   la vérité terrain), conflit injecté, contrefactuel (`data/negatives.py`), ou normal.
2. Contexte réel : la recherche de la section 7 sur le stock (index BM25 en mémoire).
   Avec la probabilité `contexte_complet`, les propositions que la cible cite et que la
   recherche n'a pas rendues sont ajoutées, dans leur pièce ; sinon, s'il en manque une,
   la cible devient ABSTENTION, sauf si une ligne qui dit le même fait (témoin de la
   vérité terrain) est dans le contexte : les manquantes sont alors ajoutées aussi.
3. Anonymiseur avec une table tirée de nouveau : indices de noms et de valeurs propres à
   l'époque et à la place.
4. Cible de la source, puis règle 4 de l'ordre des suites (§10) : un CITE d'une proposition
   qui a un conflit établi dans le contexte devient un bloc CONFLIT.
5. `encode` avec le contexte de l'automate : le masque de chaque pas (§13). Un pas de
   référence hors de son masque est une erreur.

Une transformation qui échoue (valeur non relue, conflit non trouvé, cible refusée) laisse
place à l'exemple normal de la même question, marqué `repli`. Un exemple normal qui échoue
est sauté et compté.
"""

import random
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from ccm.anonymize.encode import Encodage, Vocabulaire, encode
from ccm.anonymize.exemple import Message, anonymiser
from ccm.anonymize.table import TableConversation
from ccm.config import ChargeurConfig, DonneesConfig, GrammarConfig, IngestConfig, SearchConfig
from ccm.data import negatives
from ccm.data.publics import (
    Brut,
    Rejet,
    _cle,
    _zones,
    cible_publique,
    justificatives_de,
    stock_de,
)
from ccm.data.worldgen.cibles import _lignes, _lignes_utiles, cible_de_reference
from ccm.data.worldgen.pieces import Dossier
from ccm.data.worldgen.questions import Question
from ccm.eval.equivariance import message_de_reference, stock_de_reference
from ccm.grammar.automaton import Contexte
from ccm.grammar.lexicon import CONNECTEURS
from ccm.ingest.conflicts import detecter_conflits
from ccm.ingest.dedup import dedoublonner
from ccm.schema import Exemple, Relation
from ccm.search.bm25 import Index
from ccm.search.retrieve import chercher

ABSTENTION = ["ABSTENTION", "FIN"]
GENRES = ("abstention", "conflit", "contrefactuel")


@dataclass
class Cas:
    """Une question et son stock. `con` est une copie propre au tirage : le chargeur la
    modifie. prop_ids du stock d'origine ; `cible` lit le contexte final."""

    id: str
    origine: str
    langue: str
    con: sqlite3.Connection
    message: Message
    necessaires: list[int]  # propositions que la cible cite, dans l'ordre
    justificatives: list[int]  # retirées pour l'abstention ; transformées sinon
    cible: Callable[[Exemple, dict[int, str], sqlite3.Connection], list[str]]
    sans_reponse: bool = False  # la question n'a pas de réponse : aucune transformation
    historique: list[Message] = field(default_factory=list)  # pour l'anonymiseur
    precedentes: list[Message] = field(default_factory=list)  # pour la recherche
    citees: frozenset[int] = frozenset()
    # Vérité terrain : toutes les propositions qui disent les faits des justificatives, sous
    # une autre forme aussi. Retirées avec elles pour l'abstention ; une seule dans le
    # contexte suffit pour qu'un contexte incomplet ne devienne pas ABSTENTION.
    temoins: list[int] = field(default_factory=list)


class Source(Protocol):
    def __len__(self) -> int: ...
    def cas(self, i: int) -> Cas: ...


# --- Sources ------------------------------------------------------------------------


def stock_synthetique(d: Dossier, cfg: IngestConfig) -> sqlite3.Connection:
    """Stock de référence (§12, mentions de la vérité terrain), avec les étapes 7 et 8 de
    l'ingestion, comme tout stock que le chargeur modifie."""
    con = stock_de_reference(d, cfg)
    dedoublonner(con, cfg.doublons)
    detecter_conflits(con, cfg)
    return con


class SourceSynthetique:
    """Questions du corpus synthétique : `(dossier, questions)` en mémoire, ou les dossiers
    d'une partie écrite par `worldgen.corpus` (`depuis_corpus`)."""

    def __init__(self, dossiers: Sequence[tuple[Dossier, list[Question]]] | Sequence[Path],
                 cfg: IngestConfig, cache: int = 64):  # fmt: skip
        self.cfg = cfg
        self._dossiers = list(dossiers)
        self._places = []
        for k, x in enumerate(self._dossiers):
            n = len(x[1]) if isinstance(x, tuple) else len(_QUESTIONS.validate_json(
                (x / "questions.json").read_bytes()))  # fmt: skip
            self._places += [(k, j) for j in range(n)]
        self._charger = lru_cache(cache)(self._charger_dossier)

    @classmethod
    def depuis_corpus(cls, partie: Path, cfg: IngestConfig) -> "SourceSynthetique":
        return cls(sorted(p.parent for p in partie.glob("*/verite.json")), cfg)

    def _charger_dossier(self, k: int):
        x = self._dossiers[k]
        if not isinstance(x, tuple):
            x = (Dossier.model_validate_json((x / "verite.json").read_text(encoding="utf-8")),
                 _QUESTIONS.validate_json((x / "questions.json").read_bytes()))  # fmt: skip
        return x[0], x[1], stock_synthetique(x[0], self.cfg)

    def __len__(self) -> int:
        return len(self._places)

    def cas(self, i: int) -> Cas:
        k, j = self._places[i]
        d, questions, base = self._charger(k)
        q, cfg = questions[j], self.cfg
        lignes = _lignes(base, d)
        utiles = list(dict.fromkeys(lignes[r] for r in _lignes_utiles(q)))
        citees = frozenset(lignes[x] for t in q.historique for x in t.lignes)
        justifs = [p for p in utiles if p not in citees]
        # Toutes les lignes des événements des justificatives : la même chose dite par un
        # autre témoin, sous une autre forme de nom ou dans une autre version.
        evenement = {lignes[f"{pc.id}:{k}"]: li.evenement for pc in d.pieces
                     for k, li in enumerate(pc.lignes)}  # fmt: skip
        evs = {evenement[p] for p in justifs} - {None}
        temoins = [p for p, ev in evenement.items() if ev in evs and p not in justifs]

        def cible(ex: Exemple, valeurs: dict[int, str], con: sqlite3.Connection) -> list[str]:
            g = negatives.gardes(con)
            lignes = {r: g[p] for r, p in _lignes(con, d).items()}
            return cible_de_reference(d, q, con, ex, cfg, lignes=lignes)

        return Cas(
            q.id,
            "synthetique",
            "fr",
            negatives.copier_stock(base),
            message_de_reference(q.message, cfg),
            utiles,
            justifs,
            cible,
            sans_reponse=q.abstention,
            historique=[message_de_reference(t, cfg) for t in q.historique if t.texte],
            precedentes=[
                message_de_reference(t, cfg)
                for t in q.historique
                if t.role == "UTILISATEUR" and t.texte
            ],  # fmt: skip
            citees=citees,
            temoins=temoins,
        )


_QUESTIONS = TypeAdapter(list[Question])


class SourcePublique:
    """Questions d'un jeu public (`data.publics.Brut`) ; `zones_de` : texte → zones de noms
    (le cache de détection de la conversion)."""

    def __init__(self, bruts: Sequence[Brut], zones_de, cfg: IngestConfig):
        self.bruts, self.zones_de, self.cfg = bruts, zones_de, cfg

    def __len__(self) -> int:
        return len(self.bruts)

    def cas(self, i: int) -> Cas:
        b = self.bruts[i]
        con, ids, msg = stock_de(b, self.zones_de, self.cfg)
        justifs = justificatives_de(b, ids)

        def cible(ex: Exemple, valeurs: dict[int, str], con: sqlite3.Connection) -> list[str]:
            g = negatives.gardes(con)
            local = {p.prop_id: p.local for p in ex.propositions}
            return cible_publique(b, ex, list(dict.fromkeys(local[g[p]] for p in justifs)),
                                  valeurs)  # fmt: skip

        return Cas(b.id, b.origine, b.langue, con, msg, justifs, justifs, cible,
                   sans_reponse=b.abstention)  # fmt: skip


# --- Construction d'un exemple ------------------------------------------------------


@dataclass(frozen=True)
class Tirage:
    source: str
    exemple: Exemple
    valeurs: dict[int, str]
    encodage: Encodage
    genre: str  # normal, abstention, abstention_contexte, conflit, contrefactuel
    repli: str | None = None  # transformation tirée et abandonnée, avec sa raison


def blocs_conflit(ex: Exemple, cible: list[str]) -> list[str]:
    """§10, ordre des suites, règle 4 : un CITE (début de segment) d'une proposition qui a
    un conflit établi dans le contexte devient CONFLIT P P′ … FIN_CONFLIT, avec ses
    partenaires dans l'ordre du contexte, s'ils ne sont pas cités ailleurs."""
    voisins = defaultdict(set)
    for a, b, r in ex.relations_props:
        if r == Relation.CONFLIT:
            voisins[a].add(b)
            voisins[b].add(a)
    citees = {int(p[2:]) for p in cible if p.startswith("P:")}
    out = []
    for k, pas in enumerate(cible):
        debut = k == 0 or cible[k - 1] in CONNECTEURS
        autres = sorted(voisins[int(pas[2:])] - citees) if pas.startswith("P:") else []
        if debut and autres:
            out += ["CONFLIT", pas, *(f"P:{x}" for x in autres), "FIN_CONFLIT"]
        else:
            out.append(pas)
    return out


def completer(con: sqlite3.Connection, ordre: list[int], manquantes: list[int], p_max: int
              ) -> list[int]:  # fmt: skip
    """Ajoute les manquantes au contexte, dans leur pièce et à leur place (pièces nouvelles
    à la fin) ; au-delà de `p_max`, les dernières propositions non nécessaires sortent."""
    garder = list(ordre)
    while len(garder) + len(manquantes) > p_max and garder:
        garder.pop()
    tous = garder + manquantes
    lieu = {p: (pc, pg or 0, o or 0) for p, pc, pg, o in con.execute(
        f"SELECT prop_id, piece_id, page, ordre FROM proposition WHERE prop_id IN "
        f"({negatives._liste(tous)})")}  # fmt: skip
    rang_piece: dict[str, int] = {}
    for p in tous:
        rang_piece.setdefault(lieu[p][0], len(rang_piece))
    return sorted(tous, key=lambda p: (rang_piece[lieu[p][0]], *lieu[p][1:], p))


class Chargeur:
    def __init__(
        self,
        sources: dict[str, Source],
        cfg: ChargeurConfig,
        icfg: IngestConfig,
        scfg: SearchConfig,
        gcfg: GrammarConfig,
        voc: Vocabulaire,
        decouper: Callable[[str], Sequence[int]],
        jetons_max: int | None = None,
    ):
        self.cfg, self.icfg, self.scfg, self.gcfg = cfg, icfg, scfg, gcfg
        self.voc, self.decouper, self.jetons_max = voc, decouper, jetons_max
        self.sources = {n: s for n, s in sources.items() if len(s) and cfg.poids.get(n, 0) > 0}
        total = sum(cfg.poids[n] for n in self.sources)
        if not total:
            raise ValueError("aucune source présente avec un poids")
        self.poids = {n: cfg.poids[n] / total for n in self.sources}
        self.absentes = sorted(set(cfg.poids) - set(self.sources))
        self.bilan: Counter = Counter()

    # Plan d'une époque.
    def parts(self, n: int | None = None) -> dict[str, int]:
        """Exemples par source : plus forts restes, ordre des noms à égalité."""
        n = self.cfg.exemples_par_epoque if n is None else n
        brut = {s: w * n for s, w in self.poids.items()}
        out = {s: int(x) for s, x in brut.items()}
        for s in sorted(brut, key=lambda s: (-(brut[s] - out[s]), s))[: n - sum(out.values())]:
            out[s] += 1
        return out

    def plan(self, epoque: int, n: int | None = None) -> list[tuple[str, int]]:
        g = self.cfg.graine
        places = []
        for s, k in self.parts(n).items():
            ordre = list(range(len(self.sources[s])))
            random.Random(f"{g}:{epoque}:{s}").shuffle(ordre)
            places += [(s, ordre[i % len(ordre)]) for i in range(k)]
        random.Random(f"{g}:{epoque}").shuffle(places)
        return places

    def epoque(self, epoque: int, n: int | None = None) -> Iterator[Tirage]:
        for i, (s, j) in enumerate(self.plan(epoque, n)):
            t = self.exemple(s, j, epoque, i)
            if t is not None:
                yield t

    # Un exemple.
    def exemple(self, source: str, j: int, epoque: int, place: int) -> Tirage | None:
        rng = random.Random(f"{self.cfg.graine}:{epoque}:{place}")
        u, complet = rng.random(), rng.random() < self.cfg.contexte_complet
        graine = rng.getrandbits(32)
        try:
            cas = self.sources[source].cas(j)
        except (Rejet, KeyError, ValueError) as e:  # question qui ne se convertit pas
            self.bilan[f"sauté : {type(e).__name__}"] += 1
            return None
        genre, seuil = "normal", 0.0
        for nom, part in zip(GENRES, (self.cfg.abstention, self.cfg.conflit_injecte,
                                      self.cfg.contrefactuel), strict=True):  # fmt: skip
            seuil += part
            if genre == "normal" and u < seuil and not cas.sans_reponse:
                genre = nom
        repli = None
        if genre != "normal":
            try:
                return self._construire(source, cas, genre, complet, graine, rng)
            except (Rejet, KeyError, ValueError) as e:
                repli = f"{genre} : {e.args[0] if e.args else type(e).__name__}"
                self.bilan[f"repli {genre}"] += 1
            finally:
                cas.con.close()
            cas = self.sources[source].cas(j)
        try:
            t = self._construire(source, cas, "normal", complet, graine, rng)
        except (Rejet, KeyError, ValueError) as e:
            self.bilan[f"sauté : {type(e).__name__}"] += 1
            return None
        finally:
            cas.con.close()
        return Tirage(t.source, t.exemple, t.valeurs, t.encodage, t.genre, repli)

    def _transformer(self, cas: Cas, genre: str, rng: random.Random) -> int | None:
        """Transforme le stock ; rend la copie en conflit pour un conflit injecté."""
        cfg, con = self.cfg, cas.con
        if genre == "abstention":
            if set(cas.temoins) & cas.citees:
                raise Rejet("fait déjà cité au tour précédent")
            negatives.retirer(con, [*cas.justificatives, *cas.temoins])
            return None
        candidates = list(cas.justificatives)
        rng.shuffle(candidates)
        for p in candidates:
            if genre == "conflit":
                copie = negatives.injecter_conflit(con, p, cas.langue, self.icfg, rng,
                                                   cfg.essais_valeur)  # fmt: skip
                if copie is not None:
                    return copie
            elif negatives.contrefactuel(con, p, cas.langue, self.icfg, rng, cfg.essais_valeur):
                return None
        raise Rejet("aucune valeur changée" if genre == "contrefactuel"
                    else "conflit non trouvé par l'ingestion")  # fmt: skip

    def _construire(self, source: str, cas: Cas, genre: str, complet: bool, graine: int,
                    rng: random.Random) -> Tirage:  # fmt: skip
        con, icfg = cas.con, self.icfg
        copie = self._transformer(cas, genre, rng) if genre != "normal" else None
        g = negatives.gardes(con)
        necessaires = list(dict.fromkeys(g[p] for p in cas.necessaires if p in g))
        citees = frozenset(g[p] for p in cas.citees if p in g)
        index = Index.en_memoire(con, icfg, self.scfg)
        res = chercher(con, index, cas.message, self.scfg, icfg, precedentes=cas.precedentes,
                       citees=citees, jetons_max=self.jetons_max)  # fmt: skip
        ids = list(res.prop_ids)
        manquantes = [p for p in necessaires if p not in ids]
        fixe = ABSTENTION if genre == "abstention" else None
        temoin = any(g.get(p) in ids for p in cas.temoins)
        if fixe is None and manquantes:
            if complet or temoin:  # un témoin dans le contexte : la réponse y est
                ids = completer(con, ids, manquantes, self.scfg.budget.propositions)
            else:
                fixe, genre = ABSTENTION, "abstention_contexte"
        table = TableConversation(graine, icfg.anonymiseur.reservoir)
        ex = anonymiser(con, ids, cas.message, table, icfg, historique=cas.historique,
                        citees=citees, id=cas.id, origine=cas.origine)  # fmt: skip
        valeurs = table.valeurs()
        cible = blocs_conflit(ex, fixe or cas.cible(ex, valeurs, con))
        local = {p.prop_id: p.local for p in ex.propositions}
        if genre == "conflit" and f"P:{local.get(copie)}" not in cible:
            raise Rejet("conflit injecté hors de la cible")
        ex = Exemple.model_validate({
            **ex.model_dump(mode="json"), "langue": cas.langue, "cible": cible,
            "justificatives": [] if fixe else [local[p] for p in necessaires if p in local],
        })  # fmt: skip
        ctx = Contexte.depuis_exemple(ex, valeurs, icfg.conflits.negation)
        enc = encode(ex, self.voc, self.decouper, ctx=ctx, gcfg=self.gcfg)
        self.bilan[f"{source} {genre}"] += 1
        return Tirage(source, ex, valeurs, enc, genre)


# --- Sources réelles ----------------------------------------------------------------


class ZonesCache:
    """Zones de noms lues dans un cache de la conversion (`publics.remplir_cache`) ;
    copié en mémoire au premier appel (une copie par processus) : sur un disque dur, des
    lectures au hasard de plusieurs processus font attendre chacun."""

    def __init__(self, chemin: Path):
        self.chemin, self._con = chemin, None

    def __call__(self, texte: str):
        if self._con is None:
            disque = sqlite3.connect(f"file:{self.chemin.as_posix()}?mode=ro", uri=True)
            self._con = sqlite3.connect(":memory:")
            disque.backup(self._con)
            disque.close()
        r = self._con.execute("SELECT valeur FROM zones WHERE cle = ?", (_cle(texte),)).fetchone()
        if r is None:
            raise Rejet("texte absent du cache de détection")
        return _zones(r[0])


def sources_disponibles(dcfg: DonneesConfig, icfg: IngestConfig, corpus: Path | None = None,
                        seules: set[str] | None = None) -> dict[str, Source]:  # fmt: skip
    """Parties d'entraînement présentes sur le disque, mêmes lecteurs que `ccm convertir`.
    `corpus` : la partie d'entraînement du corpus synthétique (`worldgen.corpus`)."""
    from ccm.data import droit_questions, finqa, hotpot, squad_fr

    brut, out = dcfg.racine / "brut", {}
    if corpus is not None and corpus.exists() and (seules is None or "synthetique" in seules):
        out["synthetique"] = SourceSynthetique.depuis_corpus(corpus, icfg)
    lecteurs = {
        "hotpot": ("en", brut / "hotpot", lambda: hotpot.lire(brut / "hotpot", "train")),
        "squad": ("en", brut / "squad", lambda: squad_fr.sans_reponse(
            brut / "squad" / "train-v2.0.json")),
        "finqa": ("minuscules", brut / "finqa",
                  lambda: finqa.lire(brut / "finqa" / "train.json")[0]),
        "fquad_piaf": ("fr", brut / "piaf", lambda: squad_fr.avec_reponse(
            brut / "piaf" / "piaf-v1.2.json", "piaf", "fr", dcfg.distracteurs, dcfg.graine)),
    }  # fmt: skip
    for nom, (chaine, dossier, lire) in lecteurs.items():
        if seules is not None and nom not in seules:
            continue
        cache = dcfg.racine / f"cache-zones-{chaine}.sqlite"
        if dossier.exists() and cache.exists():
            out[nom] = SourcePublique(list(lire()), ZonesCache(cache), icfg)
    cache = dcfg.racine / droit_questions.CACHE
    if (
        (dcfg.racine / droit_questions.QUESTIONS).exists()
        and cache.exists()
        and (seules is None or "droit" in seules)
    ):
        out["droit"] = SourcePublique(droit_questions.bruts(dcfg), ZonesCache(cache), icfg)
    return out
