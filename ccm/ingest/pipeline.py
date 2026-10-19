"""Suite des étapes de l'ingestion, d'un fichier PDF au stock (SPEC.md §5).

Étapes faites : 1 (extraction), 2 (pièces et types), 3 et 3 bis (segmentation). Un
fichier déjà ingéré (même SHA-256) est ignoré. La première pièce d'un fichier porte le
nom du fichier sans extension, les suivantes `<nom>.2`, `<nom>.3`, …
"""

import hashlib
import sqlite3
from pathlib import Path

from ccm.config import IngestConfig
from ccm.graph.store import ajouter_piece, piece_connue
from ccm.ingest.extract import lire_pdf
from ccm.ingest.piece_type import decouper_pieces
from ccm.ingest.segment import segmenter


def ingerer_fichier(con: sqlite3.Connection, chemin: Path, cfg: IngestConfig) -> list[str]:
    """Ingère un PDF ; rend les identifiants des pièces ajoutées (aucune s'il est connu)."""
    sha = hashlib.sha256(chemin.read_bytes()).hexdigest()
    if piece_connue(con, sha):
        return []
    ajoutees = []
    for k, piece in enumerate(decouper_pieces(lire_pdf(chemin, cfg.extraction), cfg.pieces)):
        pid = chemin.stem if k == 0 else f"{chemin.stem}.{k + 1}"
        props, aretes = segmenter(piece, cfg)
        ajouter_piece(
            con,
            pid,
            chemin.as_posix(),
            sha,
            piece.type,
            piece.rang,
            len(piece.pages),
            [(p.page, p.texte, p.genre, p.conf) for p in props],
            aretes,
        )
        ajoutees.append(pid)
    con.commit()
    return ajoutees


def fichiers_pdf(sources: list[Path]) -> list[Path]:
    """Les PDF des sources : un fichier, ou ceux d'un dossier (triés, sans récursion)."""
    out = []
    for s in sources:
        out += sorted(s.glob("*.pdf")) if s.is_dir() else [s]
    return out
