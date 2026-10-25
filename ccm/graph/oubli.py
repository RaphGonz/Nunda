"""Suppression d'une personne : commande `ccm forget` (SPEC.md §5).

Les mentions dont la norme est dans la liste sont caviardées dans `proposition.texte`
(un « █ » par caractère : les positions des autres mentions et des nombres ne bougent
pas), ainsi que toute autre occurrence, sans casse, de leurs surfaces et des normes
(propagation, SPEC.md §6). Les mentions touchées par un caviardage et les contraintes qui
nomment une norme sont supprimées ; les mêmes chaînes sont caviardées dans `piece.chemin`
et dans les textes de `trace`. Les pièces touchées prennent une nouvelle révision ;
doublons, signatures et conflits sont recalculés. La base est ouverte avec
`secure_delete` (`schema.ouvrir_stock`), puis `VACUUM` ; l'index BM25 est reconstruit par
l'appelant.
"""

import re
import sqlite3
from collections import defaultdict

from ccm.anonymize.names import norme
from ccm.config import IngestConfig
from ccm.graph.store import revision
from ccm.ingest.conflicts import detecter_conflits
from ccm.ingest.dedup import dedoublonner

CAVIARD = "█"
_TRACE = ("question", "chemin_recherche", "contraintes", "actions")


def _caviarder(texte: str, zones) -> str:
    t = list(texte)
    for d, f in zones:
        t[d:f] = CAVIARD * (f - d)
    return "".join(t)


def oublier(con: sqlite3.Connection, noms: list[str], cfg: IngestConfig) -> int:
    """Oublie les noms (normalisés ou non) ; rend le nombre de propositions caviardées."""
    normes = sorted({norme(n, cfg.noms) for n in noms} - {""})
    if not normes:
        return 0
    q = ",".join("?" * len(normes))
    lignes = con.execute(
        f"SELECT prop_id, debut, fin, surface FROM mention WHERE norme IN ({q})", normes
    ).fetchall()
    chaines = {s for *_, s in lignes if s.strip()} | set(normes)
    motifs = [re.compile(re.escape(s), re.IGNORECASE) for s in sorted(chaines, key=len)[::-1]]

    def zones_chaines(texte: str) -> list[tuple[int, int]]:
        return [m.span() for motif in motifs for m in motif.finditer(texte)]

    zones = defaultdict(list)
    for pid, d, f, _ in lignes:
        zones[pid].append((d, f))
    pieces = set()
    for pid, piece, texte in con.execute(
        "SELECT prop_id, piece_id, texte FROM proposition"
    ).fetchall():
        z = zones[pid] + zones_chaines(texte)
        if z:
            zones[pid] = z
            pieces.add(piece)
            con.execute(
                "UPDATE proposition SET texte = ? WHERE prop_id = ?", (_caviarder(texte, z), pid)
            )
    zones = {p: z for p, z in zones.items() if z}
    for mid, pid, d, f in con.execute(
        "SELECT mention_id, prop_id, debut, fin FROM mention"
    ).fetchall():
        if any(d < zf and zd < f for zd, zf in zones.get(pid, ())):
            con.execute("DELETE FROM mention WHERE mention_id = ?", (mid,))
    con.execute(f"DELETE FROM contrainte WHERE a_norme IN ({q}) OR b_norme IN ({q})", normes * 2)
    for pid, chemin in con.execute("SELECT piece_id, chemin FROM piece").fetchall():
        if z := zones_chaines(chemin or ""):
            con.execute(
                "UPDATE piece SET chemin = ? WHERE piece_id = ?", (_caviarder(chemin, z), pid)
            )
            pieces.add(pid)
    for rid, *textes in con.execute(
        f"SELECT reponse_id, {', '.join(_TRACE)} FROM trace"
    ).fetchall():
        nouveaux = [_caviarder(t, zones_chaines(t)) if t else t for t in textes]
        if nouveaux != textes:
            con.execute(
                f"UPDATE trace SET {', '.join(c + ' = ?' for c in _TRACE)} WHERE reponse_id = ?",
                (*nouveaux, rid),
            )
    r = revision(con) + 1
    con.executemany(
        "UPDATE piece SET revision = ? WHERE piece_id = ?", [(r, p) for p in sorted(pieces)]
    )
    dedoublonner(con, cfg.doublons)
    detecter_conflits(con, cfg)
    con.commit()
    con.execute("VACUUM")
    return len(zones)
