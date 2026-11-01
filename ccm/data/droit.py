"""Découpe de textes de droit en propositions, dans un stock SQLite (SPEC.md §5, §12).

Mêmes fonctions que l'ingestion des PDF (`segmenter_paragraphes`, `ajouter_piece`), sans leur
géométrie : un texte arrive déjà en paragraphes. Seule la découpe est faite : les noms et les
nombres relèvent de la chaîne du §12, à appliquer plus tard. Un texte déjà présent (même
SHA-256) est ignoré : relancer reprend après un arrêt.
"""

import html
import multiprocessing
import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from ccm.config import IngestConfig, load_config
from ccm.graph.store import ajouter_piece
from ccm.ingest.extract import Paragraphe
from ccm.ingest.segment import PropLue, segmenter_paragraphes
from ccm.schema import GenreProposition, TypeArete, TypePiece, ouvrir_stock

_BLANCS = re.compile(r"\s+")


def net(texte: str) -> str:
    """Entités décodées (`&apos;` dans 1 758 décisions) et blancs réduits à une espace : les
    seuls changements apportés au texte."""
    return _BLANCS.sub(" ", html.unescape(texte)).strip()


@dataclass(frozen=True)
class Texte:
    """`tete` : ce qui identifie le texte (proposition EN_TETE, jamais détachée du texte).
    `paragraphes` : (texte, rangée de tableau)."""

    piece_id: str
    chemin: str
    sha256: str
    type: TypePiece
    tete: str
    paragraphes: tuple[tuple[str, bool], ...]


def decouper(t: Texte, cfg: IngestConfig) -> tuple[list[PropLue], list[tuple[int, int, TypeArete]]]:
    """Propositions du texte, l'en-tête d'abord, et leurs arêtes."""
    pars = [Paragraphe(x, 1, k, (), r) for k, (x, r) in enumerate(t.paragraphes)]
    props, aretes = segmenter_paragraphes(pars, t.type, 1, cfg)
    aretes = [(a + 1, b + 1, ty) for a, b, ty in aretes]
    if props:
        aretes.append((0, 1, TypeArete.SUIVANTE))
    return [PropLue(t.tete, GenreProposition.EN_TETE, 1, 1.0), *props], aretes


_etat: dict = {}


def _init() -> None:
    _etat["cfg"] = load_config("ingest")


def _traiter(t: Texte) -> tuple[Texte, list, list]:
    return (t, *decouper(t, _etat["cfg"]))


def ouvrir_droit(chemin: Path | str) -> sqlite3.Connection:
    """Le stock, avec les index qui gardent `ajouter_piece` rapide sur des centaines de
    milliers de pièces (`revision` cherche sinon le maximum sur toute la table)."""
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    con = ouvrir_stock(chemin)
    con.execute("CREATE INDEX IF NOT EXISTS piece_revision ON piece (revision)")
    con.execute("CREATE INDEX IF NOT EXISTS piece_sha256 ON piece (sha256)")
    return con


def ecrire_textes(
    con: sqlite3.Connection, textes: Iterable[Texte], processus: int = 1, paquet: int = 2000
) -> dict:
    """Écrit les textes nouveaux, par paquets validés un à un ; rend le bilan."""
    rang = load_config("ingest").pieces.rang
    connus = {s for (s,) in con.execute("SELECT sha256 FROM piece")}
    bilan = {"lus": 0, "deja_la": 0, "ajoutes": 0, "propositions": 0}

    def nouveaux() -> Iterator[Texte]:
        for t in textes:
            bilan["lus"] += 1
            if t.sha256 in connus:
                bilan["deja_la"] += 1
                continue
            connus.add(t.sha256)
            yield t

    flux = nouveaux()
    pool = multiprocessing.Pool(processus, _init) if processus > 1 else None
    if pool is None:
        _init()
    try:
        # Par paquets : `imap` lirait sinon tout le flux en mémoire avant le premier résultat.
        while lot := list(islice(flux, paquet)):
            sorties = pool.map(_traiter, lot, chunksize=64) if pool else map(_traiter, lot)
            for t, props, aretes in sorties:
                ajouter_piece(
                    con, t.piece_id, t.chemin, t.sha256, t.type, rang.get(t.type, 0), 1,
                    [(p.page, p.texte, p.genre, p.conf) for p in props], aretes,
                )  # fmt: skip
                bilan["ajoutes"] += 1
                bilan["propositions"] += len(props)
            con.commit()
            print(f"{bilan['lus']} lus, {bilan['ajoutes']} ajoutés", flush=True)
    finally:
        if pool:
            pool.close()
            pool.join()
    return bilan


def taille_disque(chemin: Path) -> int:
    """Octets d'un fichier ou d'un dossier."""
    if chemin.is_file():
        return chemin.stat().st_size
    return sum(f.stat().st_size for f in chemin.rglob("*") if f.is_file())
