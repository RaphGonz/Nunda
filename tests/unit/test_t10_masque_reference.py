"""T10 (SPEC.md §14) : chaque pas de chaque suite de référence est autorisé par son masque.

Dossiers synthétiques d'entraînement avec les mentions de référence (comme T4), choisis
pour couvrir tous les sous-types de question de ces dossiers et les deux blocs de conflit :
CONFLIT (conflit établi, dossier 0) et CONFLIT SANS_PREUVE (conflit supposé, dossier 10).
Mode citation, et mode synthèse quand la question en a une. Le corpus entier se contrôle
avec `python -m ccm.data.worldgen.suites`.
"""

import pytest

from ccm.config import load_config
from ccm.data.worldgen.cibles import cible_de_reference, exemple_de_reference
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.data.worldgen.suites import premier_refus
from ccm.eval.equivariance import stock_de_reference
from ccm.grammar.automaton import Contexte
from ccm.grammar.lexicon import mots

CFG = load_config("ingest")
GCFG = load_config("grammar")
WCFG = load_config("worldgen")
DOSSIERS = [0, 1, 2, 3, 4, 5, 6, 10, 11, 50]


def _suites(i):
    d = rediger_dossier(generer_monde(i, "entrainement", WCFG, frozenset()), WCFG)
    questions = poser_questions(d, WCFG)
    con = stock_de_reference(d, CFG)
    v = frozenset(m.lower() for q in questions for ph in q.synthese for e in ph.elements
                  for m in mots(e.mots))  # fmt: skip
    for q in questions:
        ex, valeurs = exemple_de_reference(d, q, con, CFG)
        ctx = Contexte.depuis_exemple(ex, valeurs, CFG.conflits.negation, v)
        for synthese in (False, True) if q.synthese else (False,):
            yield q, ctx, cible_de_reference(d, q, con, ex, CFG, synthese=synthese), synthese
    con.close()


@pytest.fixture(scope="module")
def vus():
    return {"sous_types": set(), "pas": set()}


@pytest.mark.parametrize("i", DOSSIERS)
def test_t10_chaque_pas_dans_son_masque(i, vus):
    for q, ctx, suite, synthese in _suites(i):
        assert premier_refus(ctx, suite, GCFG, synthese) is None, (q.id, synthese, suite)
        vus["sous_types"].add(f"{q.type}/{q.sous_type}")
        vus["pas"] |= set(suite) | {f"{a} {b}" for a, b in zip(suite[:-1], suite[1:], strict=True)}


def test_t10_couverture(vus):
    if len(vus["sous_types"]) == 0:
        pytest.skip("à lancer avec les tests du masque")
    types = {s.split("/")[0] for s in vus["sous_types"]}
    assert types == {"FAIT_SIMPLE", "PLUSIEURS_ETAPES", "IDENTITE", "FAIT_ABSENT", "CONFLIT",
                     "CALCUL", "DIALOGUE"}  # fmt: skip
    dialogue = {s for s in vus["sous_types"] if s.startswith("DIALOGUE/")}
    assert len(dialogue) == 5
    assert {"ABSTENTION", "SAME", "SANS_PREUVE", "NOTE_SAME", "NOTE_DIFF", "ASK_SAME",
            "CONFLIT SANS_PREUVE", "DONC CALCUL", "SYNTHESE"} <= vus["pas"]  # fmt: skip
    assert any(p.startswith("CONFLIT P:") for p in vus["pas"])  # conflit établi


def test_t10_pas_hors_du_masque_refuse():
    q, ctx, suite, _ = next(_suites(0))
    assert premier_refus(ctx, ["P:9999", *suite], GCFG, False).startswith("pas 0")
    assert premier_refus(ctx, suite[:-1], GCFG, False) == "suite non finie"
