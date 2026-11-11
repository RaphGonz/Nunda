"""T5 (SPEC.md §14, §11 « Test de propriété ») : pour toute suite tirée au hasard sous
masque, chaque caractère affiché vient de l'un des quatre ensembles : texte original d'une
proposition du contexte ou de ses dépendances et conflits, gabarit fixe, nom d'une mention
du contexte ou de la question, résultat d'un calcul sur des nombres cités. Pièce, page,
rang et numéro de citation (« ref ») sont lus dans le stock.

Dossiers synthétiques avec les mentions de référence (comme T4). En mode synthèse, les
mots libres viennent en plus du vocabulaire V (provisoire, comme T4).
"""

import pytest

from ccm.config import load_config
from ccm.data.worldgen.cibles import exemple_de_reference
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.eval.equivariance import message_de_reference, stock_de_reference
from ccm.eval.rendu import controler, fermes
from ccm.grammar.automaton import Contexte, decoder_au_hasard
from ccm.grammar.lexicon import mots
from ccm.verify.verifier import Entree, verifier

CFG = load_config("ingest")
GCFG = load_config("grammar")
VCFG = load_config("verify")
WCFG = load_config("worldgen")
GRAINES = 3


@pytest.mark.parametrize("i", [0, 1, 2, 10, 50])
def test_t5_rendu_ferme(i):
    d = rediger_dossier(generer_monde(i, "entrainement", WCFG, frozenset()), WCFG)
    questions = poser_questions(d, WCFG)
    con = stock_de_reference(d, CFG)
    v = frozenset(m.lower() for q in questions for ph in q.synthese for e in ph.elements
                  for m in mots(e.mots))  # fmt: skip
    vus = set()
    for q in questions:
        ex, valeurs = exemple_de_reference(d, q, con, CFG)
        hist = tuple(message_de_reference(t, CFG) for t in q.historique if t.texte)
        entree = Entree(ex, valeurs, message_de_reference(q.message, CFG), hist)
        textes, noms, refs = fermes(con, ex, entree)
        ctx = Contexte.depuis_exemple(ex, valeurs, CFG.conflits.negation, v)
        for g in range(GRAINES):
            for synthese in (False, True):
                suite = decoder_au_hasard(ctx, GCFG, f"{q.id}-{g}", synthese=synthese)
                rep = verifier(con, entree, suite, CFG, GCFG, VCFG, synthese=synthese,
                               vocabulaire=v)  # fmt: skip
                controler(rep, textes, noms, refs, v if synthese else frozenset())
                vus |= {f.genre for b in rep.blocs for f in b.frags}
    con.close()
    assert {"gabarit", "texte", "nom", "calcul", "ref", "mot"} <= vus


@pytest.mark.parametrize(
    "frag",
    [("gabarit", "Jean Dupont"), ("texte", "phrase inventée"), ("nom", "Inconnu"),
     ("calcul", "12 personnes"), ("ref", "P99"), ("mot", "bonjour"), ("autre", "x")],
)  # fmt: skip
def test_t5_fragment_etranger_refuse(frag):
    from ccm.verify.render import Bloc, Frag
    from ccm.verify.verifier import Reponse

    rep = Reponse([Bloc("citation", [Frag(*frag)])], [])
    with pytest.raises(AssertionError):
        controler(rep, ["Il a payé 900 euros."], {"Jean Martin"}, {"P01", "1"})
