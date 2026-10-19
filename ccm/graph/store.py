"""Écriture des pièces et des propositions dans le stock SQLite (SPEC.md §4)."""

import sqlite3

from ccm.schema import TypeArete, TypePiece


def revision(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COALESCE(MAX(revision), 0) FROM piece").fetchone()[0]


def piece_connue(con: sqlite3.Connection, sha256: str) -> bool:
    return con.execute("SELECT 1 FROM piece WHERE sha256 = ?", (sha256,)).fetchone() is not None


def ajouter_piece(
    con: sqlite3.Connection,
    piece_id: str,
    chemin: str,
    sha256: str,
    type_: TypePiece,
    rang: int,
    nb_pages: int,
    propositions: list[tuple[int, str, str, float]],  # (page, texte, genre, ocr_conf)
    aretes: list[tuple[int, int, TypeArete]],  # indices dans `propositions`
) -> list[int]:
    """Ajoute une pièce (nouvelle révision du stock) ; rend les prop_id créés."""
    con.execute(
        "INSERT INTO piece VALUES (?, ?, ?, ?, ?, ?, ?)",
        (piece_id, chemin, sha256, str(type_), rang, nb_pages, revision(con) + 1),
    )
    ids = []
    for ordre, (page, texte, genre, conf) in enumerate(propositions):
        cur = con.execute(
            "INSERT INTO proposition (piece_id, page, ordre, texte, genre, ocr_conf) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (piece_id, page, ordre, texte, str(genre), conf),
        )
        ids.append(cur.lastrowid)
    con.executemany(
        "INSERT INTO arete VALUES (?, ?, ?)", [(ids[a], ids[b], str(t)) for a, b, t in aretes]
    )
    return ids
