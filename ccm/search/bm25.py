"""Index BM25 du texte des propositions (SPEC.md §7).

Racines de l'ingestion (`ingest/racines.py`) ; les doublons non gardés sont hors de
l'index. L'index est un dossier à côté de la base (`<base>.bm25`), avec `prop_ids.json`
(le prop_id de chaque document de l'index, dans l'ordre). Le texte n'y est pas copié.
"""

import json
import shutil
import sqlite3
from pathlib import Path

import bm25s

from ccm.config import IngestConfig, SearchConfig
from ccm.ingest.racines import racines


def dossier_index(stock: Path) -> Path:
    return stock.with_name(stock.name + ".bm25")


def construire_index(
    con: sqlite3.Connection, dossier: Path, cfg: IngestConfig, cfg_s: SearchConfig
) -> int:
    """Remplace l'index du dossier ; rend le nombre de propositions indexées."""
    lignes = con.execute(
        "SELECT prop_id, texte FROM proposition "
        "WHERE groupe_doublon IS NULL OR groupe_doublon = prop_id ORDER BY prop_id"
    ).fetchall()
    if dossier.exists():
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)
    if lignes:
        bm = bm25s.BM25(k1=cfg_s.bm25.k1, b=cfg_s.bm25.b)
        bm.index([racines(t, cfg.racines) for _, t in lignes], show_progress=False)
        bm.save(dossier, show_progress=False)
    (dossier / "prop_ids.json").write_text(json.dumps([p for p, _ in lignes]), encoding="utf-8")
    return len(lignes)
