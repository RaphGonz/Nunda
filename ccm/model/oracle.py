"""Modèle oracle (SPEC.md §2, phase 3) : rejoue les actions de référence d'une question du
corpus synthétique, écrites dans le vrai contexte (stock ingéré, recherche, anonymiseur).

L'oracle lit la vérité terrain du dossier (`verite.json`, `questions.json`) et rien d'autre :
il ne voit ni nom ni texte du contexte, seulement l'exemple anonymisé et les positions du
stock. Ses pas sont ceux de `cible_de_reference`, avec les lignes du vrai stock (texte exact,
copie gardée de son groupe de doublons) et le message lu par les vrais détecteurs. Si une
ligne ou un fait de la référence manque au contexte (recherche, détection), ou si l'automate
refuse la suite, l'oracle s'abstient et dit pourquoi.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from ccm.anonymize.exemple import Message
from ccm.config import GrammarConfig, IngestConfig
from ccm.data.worldgen.cibles import cible_de_reference
from ccm.data.worldgen.pieces import Dossier
from ccm.data.worldgen.questions import Question
from ccm.data.worldgen.suites import premier_refus
from ccm.eval.conflits import _lignes_props
from ccm.grammar.automaton import Contexte
from ccm.grammar.lexicon import mots
from ccm.schema import Exemple

ABSTENTION = ["ABSTENTION", "FIN"]
NOTES = ("NOTE_SAME", "NOTE_DIFF")


@dataclass
class Decodage:
    suite: list[str]
    raison: str | None = None  # pourquoi l'oracle s'abstient au lieu de rejouer


class Oracle:
    nom = "oracle"

    def __init__(self, dossier: Path):
        self.d = Dossier.model_validate_json((dossier / "verite.json").read_text(encoding="utf-8"))
        self.questions = TypeAdapter(list[Question]).validate_json(
            (dossier / "questions.json").read_bytes()
        )
        # V provisoire (comme T4, T5, T11) : mots des synthèses de référence du dossier.
        self.vocabulaire = frozenset(
            m.lower() for q in self.questions for ph in q.synthese for e in ph.elements
            for m in mots(e.mots)
        )  # fmt: skip

    def question(self, texte: str | None = None, id: str | None = None) -> Question:
        """La question d'identifiant `id`, sinon la première de message `texte`."""
        for q in self.questions:
            if q.id == id if id else q.message.texte == texte:
                return q
        raise KeyError(f"question absente du dossier : {id or texte!r}")

    def lignes(self, con: sqlite3.Connection) -> dict[str, int]:
        """« P03:4 » → prop_id du vrai stock (copie gardée de son groupe de doublons)."""
        garde = dict(con.execute("SELECT prop_id, COALESCE(groupe_doublon, prop_id) "
                                 "FROM proposition"))  # fmt: skip
        return {f"{p}:{i}": garde[pid] for (p, i), pid in _lignes_props(con, self.d).items()}

    def decoder(
        self, con: sqlite3.Connection, q: Question, ex: Exemple, msg: Message, ctx: Contexte,
        cfg: IngestConfig, gcfg: GrammarConfig, *, synthese: bool = False, relance: bool = False,
    ) -> Decodage:  # fmt: skip
        """Suite de référence dans ce contexte. `relance` : la contrainte déclarée est déjà
        notée (SPEC.md §11, étape 8), la suite commence après NOTE_SAME ou NOTE_DIFF."""
        try:
            suite = cible_de_reference(self.d, q, con, ex, cfg, synthese,
                                       lignes=self.lignes(con), msg=msg)  # fmt: skip
        except KeyError as e:
            return Decodage(ABSTENTION, f"référence hors du contexte : {e.args[0]}")
        if relance and suite[0] in NOTES:
            suite = suite[4:] if suite[3:4] == ["ET"] else suite[3:]
        refus = premier_refus(ctx, suite, gcfg, synthese)
        return Decodage(suite) if refus is None else Decodage(ABSTENTION, f"refus : {refus}")
