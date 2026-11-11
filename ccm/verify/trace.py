"""Ligne de la table `trace` (SPEC.md §4, §11 étape 9)."""

import json
import sqlite3
import uuid
from datetime import datetime

from ccm.graph.store import revision


def ecrire_reponse(
    con: sqlite3.Connection,
    actions: dict,
    *,
    reponse_id: str | None = None,
    conv_id: str | None = None,
    question: str = "",
    prop_ids: list[int] | None = None,
    modele: str = "",
) -> str:
    """Actions et modèle de la réponse. `reponse_id` : ligne déjà écrite par la recherche
    (`search.retrieve.ecrire_trace`), complétée ; sinon une ligne neuve."""
    a = json.dumps(actions, ensure_ascii=False)
    if (
        reponse_id is not None
        and con.execute("SELECT 1 FROM trace WHERE reponse_id = ?", (reponse_id,)).fetchone()
    ):
        con.execute(
            "UPDATE trace SET actions = ?, modele = ? WHERE reponse_id = ?", (a, modele, reponse_id)
        )
        return reponse_id
    rid = reponse_id or uuid.uuid4().hex
    con.execute(
        "INSERT INTO trace (reponse_id, conv_id, question, prop_ids, actions, revision_base, "
        "modele, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, conv_id, question, json.dumps(prop_ids or []), a, revision(con), modele,
         datetime.now().isoformat(timespec="seconds")),
    )  # fmt: skip
    return rid
