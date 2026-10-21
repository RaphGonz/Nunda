"""Étape 8 de l'ingestion : conflits (SPEC.md §5).

1. Signature : le texte, chaque nom remplacé par son type (table `mention`), chaque nombre
   par `NUM:unité` et chaque date par `DATE` (table `nombre`) ; racines des autres mots,
   sans mots vides. Ensemble rangé dans `proposition.signature`, éléments séparés par
   une espace (espaces d'une unité remplacées par « _ »).
2. Candidats : Jaccard des signatures ≥ `seuil_jaccard` (MinHash LSH, puis Jaccard
   exact), noms normalisés (avec leur type) de l'une inclus dans ceux de l'autre. Seules
   les versions gardées des doublons entrent : deux propositions candidates ne sont donc
   jamais doublons l'une de l'autre.
3. Comparaison : nombres et dates alignés par unité et par ordre ; une paire alignée de
   valeurs différentes donne l'arête CONFLIT. Deux dates dont l'une est un préfixe de
   l'autre (« 2024-12 », « 2024-12-07 ») ne sont pas différentes.
4. Négation : Jaccard ≥ `seuil_negation` et une marque de négation dans une seule des deux.

L'arête CONFLIT est écrite dans les deux sens. Le calcul porte sur tout le stock et
remplace le précédent.
"""

import re
import sqlite3
from collections import defaultdict
from itertools import zip_longest

from datasketch import MinHash, MinHashLSH

from ccm.config import IngestConfig
from ccm.ingest.racines import racines
from ccm.schema import GenreNombre, TypeArete


def signature(texte: str, mentions, nombres_, cfg: IngestConfig) -> set[str]:
    """`mentions` : (début, fin, type) ; `nombres_` : (début, fin, genre, unité)."""
    sig, morceaux, pos = set(), [], 0
    zones = [(d, f, t) for d, f, t in mentions]
    zones += [(d, f, "DATE" if g == GenreNombre.DATE else f"NUM:{u}") for d, f, g, u in nombres_]
    for d, f, jeton in sorted(zones):
        if d < pos:  # zones qui se chevauchent : la première l'emporte
            continue
        morceaux.append(texte[pos:d])
        sig.add(jeton.replace(" ", "_"))
        pos = f
    morceaux.append(texte[pos:])
    return sig | set(racines(" ".join(morceaux), cfg.racines))


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b)


def _differentes(u: str, a: str, b: str) -> bool:
    if u == "date":
        return not (a.startswith(b) or b.startswith(a))
    return a != b


def _valeurs_differentes(a: dict, b: dict) -> bool:
    for u in a.keys() & b.keys():
        for x, y in zip_longest(a[u], b[u]):
            if x is not None and y is not None and _differentes(u, x, y):
                return True
    return False


def detecter_conflits(con: sqlite3.Connection, cfg: IngestConfig) -> int:
    """Recalcule les signatures et les arêtes CONFLIT du stock ; rend le nombre de paires."""
    c = cfg.conflits
    mentions, normes = defaultdict(list), defaultdict(set)
    for pid, d, f, t, n in con.execute("SELECT prop_id, debut, fin, type, norme FROM mention"):
        mentions[pid].append((d, f, t))
        normes[pid].add((n, t))
    nombres_, valeurs = defaultdict(list), defaultdict(lambda: defaultdict(list))
    for pid, d, f, g, v, u in con.execute(
        "SELECT prop_id, debut, fin, genre, valeur, unite FROM nombre ORDER BY prop_id, debut"
    ):
        nombres_[pid].append((d, f, g, u))
        valeurs[pid][u].append(v)
    negations = [re.compile(m, re.IGNORECASE) for m in c.negation]

    sigs, negatif = {}, {}
    for pid, texte, g in con.execute(
        "SELECT prop_id, texte, groupe_doublon FROM proposition"
    ).fetchall():
        sig = signature(texte, mentions[pid], nombres_[pid], cfg)
        con.execute(
            "UPDATE proposition SET signature = ? WHERE prop_id = ?", (" ".join(sorted(sig)), pid)
        )
        if (g is not None and g != pid) or not sig:
            continue
        sigs[pid] = sig
        negatif[pid] = any(m.search(texte) for m in negations)

    lsh = MinHashLSH(threshold=c.seuil_jaccard, num_perm=c.permutations)
    paires = []
    for pid, sig in sigs.items():
        mh = MinHash(num_perm=c.permutations, seed=c.graine)
        mh.update_batch([s.encode() for s in sig])
        for autre in lsh.query(mh):
            j = _jaccard(sig, sigs[autre])
            if j < c.seuil_jaccard:
                continue
            na, nb = normes[pid], normes[autre]
            if not (na <= nb or nb <= na):
                continue
            if _valeurs_differentes(valeurs[pid], valeurs[autre]) or (
                j >= c.seuil_negation and negatif[pid] != negatif[autre]
            ):
                paires.append((autre, pid))
        lsh.insert(pid, mh)

    con.execute("DELETE FROM arete WHERE type = ?", (str(TypeArete.CONFLIT),))
    con.executemany(
        "INSERT INTO arete VALUES (?, ?, ?)",
        [(a, b, str(TypeArete.CONFLIT)) for p in paires for a, b in (p, p[::-1])],
    )
    return len(paires)
