"""Suite des étapes de l'ingestion, d'un fichier PDF au stock (SPEC.md §5).

Étapes faites : 1 (extraction), 2 (pièces et types), 3 et 3 bis (segmentation), 4
(tableaux et champs), 5 (noms, SPEC.md §6), 6 (nombres et dates, hors des noms), 7 et 8
(doublons puis conflits). La propagation des noms, les doublons et les conflits sont
recalculés sur tout le stock après les fichiers. Un fichier déjà ingéré (même SHA-256) est ignoré.
La première pièce d'un fichier porte le nom du fichier sans extension, les suivantes
`<nom>.2`, `<nom>.3`, …
"""

import hashlib
import sqlite3
from pathlib import Path

from ccm.config import IngestConfig
from ccm.graph.store import ajouter_nombres, ajouter_piece, piece_connue
from ccm.ingest.conflicts import detecter_conflits
from ccm.ingest.dedup import dedoublonner
from ccm.ingest.extract import lire_pdf
from ccm.ingest.numbers import nombres
from ccm.ingest.piece_type import decouper_pieces
from ccm.ingest.segment import segmenter
from ccm.ner.propagate import ecrire_mentions, propager_stock
from ccm.ner.union import detecter


def ingerer_fichier(con: sqlite3.Connection, chemin: Path, cfg: IngestConfig) -> list[str]:
    """Ingère un PDF ; rend les identifiants des pièces ajoutées (aucune s'il est connu)."""
    sha = hashlib.sha256(chemin.read_bytes()).hexdigest()
    if piece_connue(con, sha):
        return []
    ajoutees, lues = [], []
    for k, piece in enumerate(decouper_pieces(lire_pdf(chemin, cfg.extraction), cfg.pieces)):
        pid = chemin.stem if k == 0 else f"{chemin.stem}.{k + 1}"
        props, aretes = segmenter(piece, cfg)
        ids = ajouter_piece(
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
        lues += zip(ids, (p.texte for p in props), strict=True)
        ajoutees.append(pid)
    zones = detecter([t for _, t in lues], cfg)
    for (i, texte), zs in zip(lues, zones, strict=True):
        ecrire_mentions(con, i, texte, zs, cfg)
        ajouter_nombres(con, i, nombres(texte, cfg.nombres, [(z.debut, z.fin) for z in zs]))
    con.commit()
    return ajoutees


def ingerer_fichiers(con: sqlite3.Connection, fichiers: list[Path], cfg: IngestConfig) -> list[str]:
    """Ingère les fichiers, puis recalcule la propagation des noms, les doublons et les
    conflits du stock ; rend les pièces ajoutées."""
    ajoutees = [p for f in fichiers for p in ingerer_fichier(con, f, cfg)]
    propager_stock(con, cfg)
    dedoublonner(con, cfg.doublons)
    detecter_conflits(con, cfg)
    con.commit()
    return ajoutees


def fichiers_pdf(sources: list[Path]) -> list[Path]:
    """Les PDF des sources : un fichier, ou ceux d'un dossier (triés, sans récursion)."""
    out = []
    for s in sources:
        out += sorted(s.glob("*.pdf")) if s.is_dir() else [s]
    return out
