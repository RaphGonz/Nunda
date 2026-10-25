"""Graphe du stock pour la recherche (SPEC.md §7) : index inversé norme de nom →
propositions, noms reliés, extension (étape 2), fermeture (étape 6), jetons.

Seules les propositions gardées (hors doublons non gardés) y entrent, comme dans l'index
BM25.
"""

import math
import sqlite3
from collections import defaultdict

from ccm.anonymize.relations import Nom, relations_entre
from ccm.config import IngestConfig, SearchConfig
from ccm.schema import TypeArete, TypeNom


def jetons(texte: str, cfg: SearchConfig) -> int:
    """Jetons d'une proposition dans le contexte, en attendant le tokenizer."""
    return cfg.jetons.par_proposition + math.ceil(cfg.jetons.par_mot * len(texte.split()))


class Graphe:
    def __init__(self, con: sqlite3.Connection):
        self.props: dict[int, tuple[str, int, int, str]] = {
            p: (piece, page or 0, ordre or 0, texte)
            for p, piece, page, ordre, texte in con.execute(
                "SELECT prop_id, piece_id, page, ordre, texte FROM proposition "
                "WHERE groupe_doublon IS NULL OR groupe_doublon = prop_id"
            )
        }
        self.mentions: dict[int, list[tuple[str, TypeNom]]] = defaultdict(list)
        self.par_norme: dict[str, set[int]] = defaultdict(set)
        surfaces: dict[tuple[str, TypeNom], set[str]] = defaultdict(set)
        for p, norme, type_, surface in con.execute(
            "SELECT prop_id, norme, type, surface FROM mention ORDER BY prop_id, debut"
        ):
            if p in self.props:
                self.mentions[p].append((norme, TypeNom(type_)))
                self.par_norme[norme].add(p)
                surfaces[(norme, TypeNom(type_))].add(surface)
        self.noms = [Nom(n, t, frozenset(s)) for (n, t), s in sorted(surfaces.items())]
        # Arêtes dans les deux sens ; `depend` : sens de la dépendance seulement.
        self.voisins: dict[str, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        self.depend: dict[int, set[int]] = defaultdict(set)
        for a, b, t in con.execute("SELECT src, dst, type FROM arete"):
            if a in self.props and b in self.props:
                self.voisins[t][a].add(b)
                self.voisins[t][b].add(a)
                if t == TypeArete.DEPEND_DE:
                    self.depend[a].add(b)

    def relies(self, nom: Nom, cfg_s: SearchConfig, cfg: IngestConfig) -> list[str]:
        """Normes reliées à `nom` par les relations de l'étape 1 (sans la sienne)."""
        rels = set(cfg_s.departs.relations)
        return sorted(
            {
                n.norme
                for n in self.noms
                if n.norme != nom.norme and relations_entre(nom, n, cfg) & rels
            }
        )

    def extension(self, p: int) -> list[tuple[int, str]]:
        """Étape 2 : un saut par SUIVANTE et CONFLIT ; DEPEND_DE en fermeture complète."""
        out = [(q, str(t)) for t in (TypeArete.SUIVANTE, TypeArete.CONFLIT)
               for q in self.voisins[t].get(p, ())]  # fmt: skip
        vus, pile = {p}, [p]
        while pile:
            for q in self.voisins[TypeArete.DEPEND_DE].get(pile.pop(), ()):
                if q not in vus:
                    vus.add(q)
                    pile.append(q)
                    out.append((q, str(TypeArete.DEPEND_DE)))
        return sorted(out)

    def fermeture(self, p: int) -> set[int]:
        """Étape 6 : la proposition, ses dépendances et ses conflits, jusqu'au point fixe."""
        vus, pile = {p}, [p]
        while pile:
            q = pile.pop()
            for r in self.depend.get(q, set()) | self.voisins[TypeArete.CONFLIT].get(q, set()):
                if r not in vus:
                    vus.add(r)
                    pile.append(r)
        return vus
