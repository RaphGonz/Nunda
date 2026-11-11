"""Exemples négatifs et difficiles (SPEC.md §12) : transformations du stock d'une question.

Le chargeur (`train/chargeur.py`) les applique à une copie en mémoire du stock, avant la
recherche. Après chaque ajout, les étapes 7 et 8 de l'ingestion (`dedoublonner`,
`detecter_conflits`) sont relancées sur tout le stock : une arête CONFLIT vient toujours du
code de l'ingestion, jamais de la transformation.

- **Abstention** : `retirer` les justificatives et leurs doublons.
- **Conflit injecté** : `injecter_conflit` copie une justificative dans une nouvelle pièce
  d'un autre rang et change une valeur ; gardé si l'ingestion trouve le conflit.
- **Contrefactuel** : `contrefactuel` change une valeur de la justificative et ajoute sa
  forme d'origine (« habituelle ») dans une pièce sans rapport ; cette pièce est retirée si
  l'ingestion la trouve en conflit avec la justificative (la cible doit rester un CITE).

Une valeur change par ses chiffres : même nombre de chiffres, donc mêmes positions dans
le texte ; le nombre est relu par l'extraction de l'ingestion à la même place.
"""

import random
import re
import sqlite3
from collections.abc import Iterable

from ccm.config import IngestConfig
from ccm.data.publics import _nombres
from ccm.graph.store import ajouter_piece
from ccm.ingest.conflicts import detecter_conflits
from ccm.ingest.dedup import dedoublonner
from ccm.schema import GenreNombre, TypeArete, TypePiece

RANGS = range(5)  # ⟨RANG:0⟩ … ⟨RANG:4⟩ (SPEC.md §8)


def copier_stock(con: sqlite3.Connection) -> sqlite3.Connection:
    con.commit()  # une transaction ouverte bloque `backup`
    copie = sqlite3.connect(":memory:")
    con.backup(copie)
    return copie


def gardes(con: sqlite3.Connection) -> dict[int, int]:
    """prop_id → version gardée de son groupe de doublons."""
    return dict(con.execute("SELECT prop_id, COALESCE(groupe_doublon, prop_id) FROM proposition"))


def _liste(ids: Iterable[int]) -> str:
    return ",".join(str(int(p)) for p in ids) or "NULL"


def retirer(con: sqlite3.Connection, prop_ids: Iterable[int], doublons: bool = True) -> set[int]:
    """Retire les propositions (et, avec `doublons`, toutes les copies de leurs groupes) ;
    rend les prop_ids retirés. Les pièces vides sont retirées aussi."""
    ids = set(prop_ids)
    if doublons:
        g = {gardes(con).get(p, p) for p in ids}
        ids |= {p for (p,) in con.execute(
            f"SELECT prop_id FROM proposition WHERE groupe_doublon IN ({_liste(g)})")}  # fmt: skip
    liste = _liste(ids)
    con.execute(f"DELETE FROM mention WHERE prop_id IN ({liste})")
    con.execute(f"DELETE FROM nombre WHERE prop_id IN ({liste})")
    con.execute(f"DELETE FROM arete WHERE src IN ({liste}) OR dst IN ({liste})")
    con.execute(f"DELETE FROM proposition WHERE prop_id IN ({liste})")
    con.execute("DELETE FROM piece WHERE piece_id NOT IN (SELECT piece_id FROM proposition)")
    return ids


def _reingerer(con: sqlite3.Connection, cfg: IngestConfig) -> None:
    dedoublonner(con, cfg.doublons)
    detecter_conflits(con, cfg)


def copier_proposition(
    con: sqlite3.Connection, prop_id: int, piece_id: str, type_: TypePiece, rang: int
) -> int:
    """Nouvelle pièce d'une seule proposition, copie de `prop_id` (texte, mentions, nombres)."""
    texte, genre, conf = con.execute(
        "SELECT texte, genre, ocr_conf FROM proposition WHERE prop_id = ?", (prop_id,)
    ).fetchone()
    [nouveau] = ajouter_piece(con, piece_id, "", piece_id, type_, rang, 1,
                              [(1, texte, genre, conf)], [])  # fmt: skip
    con.execute(
        "INSERT INTO mention (prop_id, debut, fin, surface, norme, type, detecteurs) "
        "SELECT ?, debut, fin, surface, norme, type, detecteurs FROM mention WHERE prop_id = ?",
        (nouveau, prop_id),
    )
    con.execute(
        "INSERT INTO nombre (prop_id, debut, fin, surface, genre, valeur, unite, precision_date) "
        "SELECT ?, debut, fin, surface, genre, valeur, unite, precision_date FROM nombre "
        "WHERE prop_id = ?",
        (nouveau, prop_id),
    )
    return nouveau


def _chiffres(n: int, interdit: str, rng: random.Random) -> str:
    while True:
        s = "".join(str(rng.randrange(1 if (k == 0 and n > 1) else 0, 10)) for k in range(n))
        if s != interdit:
            return s


def changer_valeur(
    con: sqlite3.Connection, prop_id: int, langue: str, cfg: IngestConfig, rng: random.Random,
    essais: int,
) -> bool:  # fmt: skip
    """Change un nombre (genre NUM) de la proposition ; False si aucun essai n'est relu par
    l'extraction comme un nombre de même genre et de même unité, à la même place."""
    (texte,) = con.execute("SELECT texte FROM proposition WHERE prop_id = ?", (prop_id,)).fetchone()
    nombres = con.execute(
        "SELECT nombre_id, debut, fin, valeur, unite FROM nombre WHERE prop_id = ? AND genre = ? "
        "ORDER BY debut",
        (prop_id, str(GenreNombre.NUM)),
    ).fetchall()
    nombres = [n for n in nombres if re.search(r"\d", texte[n[1] : n[2]])]
    zones = con.execute("SELECT debut, fin FROM mention WHERE prop_id = ?", (prop_id,)).fetchall()
    for _ in range(essais if nombres else 0):
        nid, d, f, valeur, unite = rng.choice(nombres)
        m = rng.choice(list(re.finditer(r"\d+", texte[d:f])))
        a, b = d + m.start(), d + m.end()
        nouveau = texte[:a] + _chiffres(b - a, texte[a:b], rng) + texte[b:]
        lu = next((x for x in _nombres(nouveau, zones, langue, cfg) if (x.debut, x.fin) == (d, f)),
                  None)  # fmt: skip
        if lu is None or lu.genre != GenreNombre.NUM or lu.unite != unite or lu.valeur == valeur:
            continue
        con.execute("UPDATE proposition SET texte = ? WHERE prop_id = ?", (nouveau, prop_id))
        con.execute("UPDATE nombre SET surface = ?, valeur = ? WHERE nombre_id = ?",
                    (nouveau[d:f], lu.valeur, nid))  # fmt: skip
        return True
    return False


def _piece(con: sqlite3.Connection, prop_id: int) -> tuple[str, TypePiece, int]:
    piece, type_, rang = con.execute(
        "SELECT p.piece_id, pc.type, pc.rang FROM proposition p JOIN piece pc USING (piece_id) "
        "WHERE p.prop_id = ?",
        (prop_id,),
    ).fetchone()
    return piece, TypePiece(type_), rang


def en_conflit(con: sqlite3.Connection, a: int, b: int) -> bool:
    return con.execute("SELECT 1 FROM arete WHERE src = ? AND dst = ? AND type = ?",
                       (a, b, str(TypeArete.CONFLIT))).fetchone() is not None  # fmt: skip


def injecter_conflit(
    con: sqlite3.Connection, prop_id: int, langue: str, cfg: IngestConfig, rng: random.Random,
    essais: int,
) -> int | None:  # fmt: skip
    """prop_id de la copie en conflit avec `prop_id` ; None (stock inchangé) si l'ingestion
    ne trouve pas le conflit (§5 : même fait, valeur différente)."""
    piece, type_, rang = _piece(con, prop_id)
    copie = copier_proposition(con, prop_id, f"{piece}~conflit", type_,
                               rng.choice([r for r in RANGS if r != rang]))  # fmt: skip
    if changer_valeur(con, copie, langue, cfg, rng, essais):
        _reingerer(con, cfg)
        if en_conflit(con, gardes(con)[prop_id], copie):
            return copie
    retirer(con, [copie], doublons=False)
    _reingerer(con, cfg)
    return None


def contrefactuel(
    con: sqlite3.Connection, prop_id: int, langue: str, cfg: IngestConfig, rng: random.Random,
    essais: int,
) -> bool:  # fmt: skip
    """Change une valeur de `prop_id` ; sa forme d'origine va dans une pièce sans rapport.
    False (stock inchangé) si aucune valeur ne change."""
    piece, _, _ = _piece(con, prop_id)
    habituelle = copier_proposition(con, prop_id, f"{piece}~habituelle", TypePiece.AUTRE, 0)
    if not changer_valeur(con, prop_id, langue, cfg, rng, essais):
        retirer(con, [habituelle], doublons=False)
        return False
    _reingerer(con, cfg)
    g = gardes(con)
    if en_conflit(con, g[prop_id], g[habituelle]):
        retirer(con, [habituelle], doublons=False)
        _reingerer(con, cfg)
    return True
