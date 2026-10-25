"""Étape 7 de l'ingestion : doublons (SPEC.md §5).

Copies exactes : même empreinte SHA-1 du texte normalisé (NFKC, minuscules, blancs
réduits). Quasi-copies : MinHash (datasketch) sur les triplets de mots, candidats par LSH,
puis Jaccard exact des triplets ≥ `seuil_jaccard`. Un texte de moins de trois mots n'a que
des copies exactes. Dans un groupe, la version gardée est la copie de meilleure confiance
OCR (à égalité, la première ingérée) ; `groupe_doublon` de chaque copie vaut le prop_id
de la version gardée, et chaque autre copie reçoit l'arête DOUBLON_DE vers elle. Le calcul
porte sur tout le stock et remplace le précédent.
"""

import hashlib
import sqlite3
import unicodedata

from datasketch import MinHash, MinHashLSH

from ccm.config import DoublonsConfig
from ccm.schema import TypeArete


def normaliser(texte: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", texte).casefold().split())


def _triplets(mots: list[str], n: int) -> set[str]:
    return {" ".join(mots[k : k + n]) for k in range(len(mots) - n + 1)}


def dedoublonner(con: sqlite3.Connection, cfg: DoublonsConfig) -> int:
    """Recalcule les groupes de doublons du stock ; rend le nombre de groupes."""
    props = con.execute("SELECT prop_id, texte, ocr_conf FROM proposition ORDER BY prop_id")
    parent: dict[int, int] = {}
    conf: dict[int, float] = {}

    def racine(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    exactes: dict[bytes, int] = {}
    triplets: dict[int, set[str]] = {}
    for pid, texte, c in props:
        parent[pid], conf[pid] = pid, c
        norme = normaliser(texte)
        cle = hashlib.sha1(norme.encode()).digest()
        if cle in exactes:
            parent[pid] = exactes[cle]
        else:
            exactes[cle] = pid
            mots = norme.split()
            if len(mots) >= cfg.mots_par_triplet:
                triplets[pid] = _triplets(mots, cfg.mots_par_triplet)

    lsh = MinHashLSH(threshold=cfg.seuil_jaccard, num_perm=cfg.permutations)
    for pid, ts in triplets.items():
        mh = MinHash(num_perm=cfg.permutations, seed=cfg.graine)
        mh.update_batch([t.encode() for t in ts])
        for autre in lsh.query(mh):
            commun = len(ts & triplets[autre])
            if commun / (len(ts) + len(triplets[autre]) - commun) >= cfg.seuil_jaccard:
                parent[racine(pid)] = racine(autre)
        lsh.insert(pid, mh)

    groupes: dict[int, list[int]] = {}
    for pid in parent:
        groupes.setdefault(racine(pid), []).append(pid)
    groupes = {r: g for r, g in groupes.items() if len(g) > 1}
    con.execute("UPDATE proposition SET groupe_doublon = NULL")
    con.execute("DELETE FROM arete WHERE type = ?", (str(TypeArete.DOUBLON_DE),))
    for g in groupes.values():
        garde = max(g, key=lambda p: (conf[p], -p))
        con.executemany(
            "UPDATE proposition SET groupe_doublon = ? WHERE prop_id = ?", [(garde, p) for p in g]
        )
        con.executemany(
            "INSERT INTO arete VALUES (?, ?, ?)",
            [(p, garde, str(TypeArete.DOUBLON_DE)) for p in g if p != garde],
        )
    return len(groupes)
