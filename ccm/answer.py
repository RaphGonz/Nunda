"""Réponse de bout en bout (SPEC.md §2, phase 3 ; §7, §6, §10, §11) : lecture du message,
recherche, anonymiseur, modèle (l'oracle en phase 3), vérificateur, une relance après une
contrainte notée (NOTE_SAME, NOTE_DIFF)."""

import sqlite3
from dataclasses import dataclass, field

from ccm.anonymize.exemple import anonymiser, lire_message
from ccm.anonymize.table import TableConversation
from ccm.config import GrammarConfig, IngestConfig, SearchConfig, VerifyConfig
from ccm.data.worldgen.questions import Question
from ccm.grammar.automaton import Contexte
from ccm.model.oracle import Oracle
from ccm.search.bm25 import Index
from ccm.search.retrieve import chercher, ecrire_trace
from ccm.verify.verifier import Entree, Reponse, verifier


@dataclass
class Tour:
    """Un passage dans la chaîne : entrée du vérificateur (exemple, valeurs, messages), pas
    du modèle."""

    entree: Entree
    suite: list[str]
    raison: str | None  # abstention de l'oracle faute de pouvoir rejouer la référence


@dataclass
class Resultat:
    reponse: Reponse
    tours: list[Tour] = field(default_factory=list)


def repondre(
    con: sqlite3.Connection, index: Index, oracle: Oracle, q: Question, cfg: IngestConfig,
    cfg_s: SearchConfig, gcfg: GrammarConfig, vcfg: VerifyConfig, *, conv_id: str,
    synthese: bool = False, graine: int = 0,
) -> Resultat:  # fmt: skip
    """Réponse vérifiée à la question `q` (message et historique du dossier de l'oracle)."""
    msg = lire_message(q.message.texte, con, cfg)
    precedentes = [lire_message(t.texte, con, cfg) for t in q.historique
                   if t.role == "UTILISATEUR" and t.texte]  # fmt: skip
    historique = tuple(lire_message(t.texte, con, cfg) for t in q.historique if t.texte)
    lignes = oracle.lignes(con)
    modele = [t for t in q.historique if t.role == "MODELE"]
    citees = frozenset(lignes[x] for x in (modele[-1].lignes if modele else ()) if x in lignes)
    out = Resultat(None)  # type: ignore[arg-type]

    def tour(relance: bool) -> Reponse:
        res = chercher(con, index, msg, cfg_s, cfg, precedentes=precedentes, conv_id=conv_id,
                       citees=citees)  # fmt: skip
        rid = ecrire_trace(con, res, q.message.texte, conv_id)
        table = TableConversation(graine, cfg.anonymiseur.reservoir)
        ex = anonymiser(con, res.prop_ids, msg, table, cfg, historique=historique,
                        conv_id=conv_id, citees=citees, id=q.id)  # fmt: skip
        valeurs = table.valeurs()
        ctx = Contexte.depuis_exemple(ex, valeurs, cfg.conflits.negation, oracle.vocabulaire)
        dec = oracle.decoder(con, q, ex, msg, ctx, cfg, gcfg, synthese=synthese, relance=relance)
        e = Entree(ex, valeurs, msg, historique, conv_id=conv_id, reponse_id=rid)
        out.tours.append(Tour(e, dec.suite, dec.raison))
        return verifier(con, e, dec.suite, cfg, gcfg, vcfg, synthese=synthese,
                        vocabulaire=oracle.vocabulaire, modele=oracle.nom,
                        relancer=None if relance else lambda: tour(True))  # fmt: skip

    out.reponse = tour(False)
    con.commit()
    return out
