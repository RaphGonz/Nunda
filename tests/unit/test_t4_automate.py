"""T4 (SPEC.md §14) : l'automate accepte toutes les suites de référence ; les décodages
au hasard sous masque n'ont aucune impasse et finissent en 96 pas au plus. T10 : chaque
pas d'une suite de référence est autorisé par son masque.

Dossiers synthétiques avec les mentions de référence (comme T2). La synthèse (§10 bis) est
contrôlée avec un vocabulaire V provisoire : les mots des synthèses de référence du
dossier (la liste V de §10 bis attend le corpus de la phase 5).
"""

import pytest

from ccm.config import load_config
from ccm.data.worldgen.cibles import cible_de_reference, exemple_de_reference
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.eval.equivariance import stock_de_reference
from ccm.grammar.automaton import Automate, Contexte, decoder_au_hasard
from ccm.grammar.lexicon import mots

CFG = load_config("ingest")
GCFG = load_config("grammar")
WCFG = load_config("worldgen")


def _dossier(i):
    d = rediger_dossier(generer_monde(i, "entrainement", WCFG, frozenset()), WCFG)
    return d, poser_questions(d, WCFG), stock_de_reference(d, CFG)


def _verifier(ctx, suite, synthese):
    """T10 et T4 : chaque pas dans son masque, fin acceptée."""
    a = Automate(ctx, GCFG, synthese=synthese)
    for k, pas in enumerate(suite):
        assert pas in a.autorises(), (k, pas, suite)
        a.avancer(pas)
    assert a.fini


@pytest.mark.parametrize("i", [0, 1, 2, 50])  # 50 : ASK_SAME à trois personnes possibles
def test_t4_suites_de_reference(i):
    d, questions, con = _dossier(i)
    v = frozenset(m.lower() for q in questions for ph in q.synthese for e in ph.elements
                  for m in mots(e.mots))  # fmt: skip
    types = set()
    for q in questions:
        ex, valeurs = exemple_de_reference(d, q, con, CFG)
        ctx = Contexte.depuis_exemple(ex, valeurs, CFG.conflits.negation, v)
        suite = cible_de_reference(d, q, con, ex, CFG)
        assert len(suite) <= GCFG.pas_max, q.id
        _verifier(ctx, suite, synthese=False)
        if q.synthese:
            suite = cible_de_reference(d, q, con, ex, CFG, synthese=True)
            assert "SYNTHESE" in suite and len(suite) <= GCFG.pas_max_synthese
            _verifier(ctx, suite, synthese=True)
        types.add(q.type)
    assert types >= {"FAIT_SIMPLE", "PLUSIEURS_ETAPES", "IDENTITE", "CALCUL", "DIALOGUE",
                     "FAIT_ABSENT"}  # fmt: skip


@pytest.mark.parametrize("synthese", [False, True])
def test_t4_decodages_aleatoires(synthese):
    d, questions, con = _dossier(0)
    v = frozenset({"a", "le", "la", "de", ".", "ne", "pas", "signé"})
    pas_max = GCFG.pas_max_synthese if synthese else GCFG.pas_max
    n = 0
    for q in questions:
        ex, valeurs = exemple_de_reference(d, q, con, CFG)
        ctx = Contexte.depuis_exemple(ex, valeurs, CFG.conflits.negation, v)
        for graine in range(25):
            suite = decoder_au_hasard(ctx, GCFG, graine, synthese=synthese)  # impasse : erreur
            assert suite[-1] == "FIN" and len(suite) <= pas_max
            n += 1
    assert n >= 900
