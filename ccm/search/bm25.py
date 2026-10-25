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

from ccm.config import IngestConfig, RacinesConfig, SearchConfig
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


class Index:
    """Index BM25 chargé : score de chaque proposition gardée pour un texte."""

    def __init__(self, dossier: Path):
        self.prop_ids: list[int] = json.loads((dossier / "prop_ids.json").read_text("utf-8"))
        self.bm = bm25s.BM25.load(dossier) if self.prop_ids else None

    def scores(self, texte: str, cfg: RacinesConfig) -> dict[int, float]:
        """Scores non nuls, par prop_id."""
        mots = [m for m in racines(texte, cfg) if self.bm and m in self.bm.vocab_dict]
        if not mots:
            return {}
        s = self.bm.get_scores(mots)
        return {self.prop_ids[i]: float(s[i]) for i in s.nonzero()[0]}


def charger_index(dossier: Path) -> Index:
    return Index(dossier)
