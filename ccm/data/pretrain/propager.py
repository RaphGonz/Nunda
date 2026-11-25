"""Propagation des noms dans le corpus de pré-entraînement (SPEC.md §6), en deux passes.

Passe A, document par document : `propager` (`ccm/ner/propagate.py`) masque dans tout le
document une chaîne détectée une fois. On compte en même temps, pour chaque chaîne (surface
exacte, comme `propager`), ses occurrences détectées par les détecteurs et ses documents.

Passe B : pour les chaînes détectées dans au moins `documents_min` documents, un automate
d'Aho-Corasick compte toutes leurs occurrences dans le corpus, entre deux limites de mot. La
liste globale garde les chaînes détectées dans au moins `part_min` de leurs occurrences ; elle
est ensuite appliquée à chaque document. Les comptes vivent dans un fichier sqlite de travail
(`travail/chaines.sqlite`), hors du corpus : jamais en mémoire, jamais dans un fichier
d'entraînement.
"""

import pickle
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

import ahocorasick

from ccm.ner.detectors import Zone
from ccm.ner.propagate import _PROPAGATION, _nouvelle
from ccm.ner.union import _PRIORITE, unir
from ccm.schema import TypeNom

_TYPES = list(TypeNom)  # rang de priorité → type


def comptes_detectes(phrases: list[str], zones: list[list[Zone]], longueur_min: int
                     ) -> dict[str, tuple[int, int]]:  # fmt: skip
    """Chaîne → (occurrences détectées dans le document, rang du type le plus prioritaire)."""
    out: dict[str, tuple[int, int]] = {}
    for t, zs in zip(phrases, zones, strict=True):
        for z in zs:
            s = t[z.debut : z.fin]
            if len(s) >= longueur_min:
                n, r = out.get(s, (0, len(_TYPES)))
                out[s] = (n + 1, min(r, _PRIORITE[z.type]))
    return out


def ouvrir_chaines(chemin: Path) -> sqlite3.Connection:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(chemin)
    con.execute("CREATE TABLE IF NOT EXISTS chaine (chaine TEXT PRIMARY KEY, rang INTEGER, "
                "detectees INTEGER, documents INTEGER, occurrences INTEGER DEFAULT 0)")  # fmt: skip
    return con


def ajouter_detectees(con: sqlite3.Connection, lignes: Iterable[tuple[str, int, int, int]]) -> None:
    """(chaîne, rang, détectées, documents) d'un paquet, ajoutées aux comptes."""
    con.executemany(
        "INSERT INTO chaine (chaine, rang, detectees, documents) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (chaine) DO UPDATE SET rang = min(rang, excluded.rang), "
        "detectees = detectees + excluded.detectees, documents = documents + excluded.documents",
        lignes,
    )


def ajouter_occurrences(con: sqlite3.Connection, comptes: Iterable[tuple[str, int]]) -> None:
    con.executemany("UPDATE chaine SET occurrences = occurrences + ? WHERE chaine = ?",
                    ((n, s) for s, n in comptes))  # fmt: skip


def candidates(con: sqlite3.Connection, documents_min: int) -> Iterator[tuple[str, int]]:
    yield from con.execute(
        "SELECT chaine, rang FROM chaine WHERE documents >= ? ORDER BY chaine", (documents_min,)
    )


def globales(con: sqlite3.Connection, documents_min: int, part_min: float
             ) -> Iterator[tuple[str, int]]:  # fmt: skip
    """Liste globale : détectée dans au moins `part_min` de ses occurrences."""
    yield from con.execute(
        "SELECT chaine, rang FROM chaine WHERE documents >= ? AND occurrences > 0 "
        "AND detectees >= ? * occurrences ORDER BY chaine",
        (documents_min, part_min),
    )


def automate(chaines: Iterable[tuple[str, int]]) -> ahocorasick.Automaton:
    a = ahocorasick.Automaton()
    for s, rang in chaines:
        a.add_word(s, (s, rang))
    if len(a):
        a.make_automaton()
    return a


def sauver(a: ahocorasick.Automaton, chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    partiel = chemin.with_name(chemin.name + ".part")
    with partiel.open("wb") as f:
        pickle.dump(a, f)
    partiel.replace(chemin)


def charger(chemin: Path) -> ahocorasick.Automaton:
    with chemin.open("rb") as f:
        return pickle.load(f)


def _mot(c: str) -> bool:
    return c.isalnum() or c == "_"


def occurrences(a: ahocorasick.Automaton, texte: str) -> Iterator[tuple[int, int, str, int]]:
    """(début, fin, chaîne, rang) de chaque occurrence entre deux limites de mot."""
    if not len(a):
        return
    for fin, (s, rang) in a.iter(texte):
        d, f = fin - len(s) + 1, fin + 1
        if (d == 0 or not _mot(texte[d - 1])) and (f == len(texte) or not _mot(texte[f])):
            yield d, f, s, rang


def compter_occurrences(a: ahocorasick.Automaton, textes: Iterable[str]) -> Counter:
    return Counter(s for t in textes for _, _, s, _ in occurrences(a, t))


def appliquer(a: ahocorasick.Automaton, texte: str, zones: list[Zone]) -> list[Zone]:
    """Ajoute les occurrences des chaînes de la liste globale, puis fusionne (`unir`)."""
    nouvelles = [Zone(d, f, _TYPES[r], _PROPAGATION) for d, f, _, r in occurrences(a, texte)
                 if _nouvelle(zones, d, f, _TYPES[r])]  # fmt: skip
    return unir(zones + nouvelles) if nouvelles else zones
