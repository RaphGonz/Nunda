"""Grammaire (SPEC.md §10, §10 bis) : lexique, algèbre des unités, règles du masque."""

from datetime import date
from decimal import Decimal

import pytest

from ccm.config import load_config
from ccm.grammar.automaton import Automate, Contexte, accepter, decoder_au_hasard
from ccm.grammar.lexicon import CONNECTEURS, LEXIQUE, LEXIQUE_COMPLET, NAVIGATION
from ccm.grammar.units import Valeur, appliquer
from ccm.schema import Exemple

CFG = load_config("grammar")
NEGATION = load_config("ingest").conflits.negation


def _nom(t, n):
    return {"genre": "NOM", "type": t, "nom": n}


def _num(unite, vid):
    return {"genre": "NUM", "unite": unite, "grandeur": 0, "rang_valeur": 0, "valeur_id": vid,
            "signe": 1}  # fmt: skip


def _date(vid):
    return {"genre": "DATE", "unite": "date", "grandeur": None, "rang_valeur": 0,
            "valeur_id": vid, "precision": "JOUR"}  # fmt: skip


def _texte(marques, mots="a payé"):
    return {"texte": " ".join(f"⟦{i}⟧" for i in range(len(marques))) + f" {mots}.",
            "marques": marques}  # fmt: skip


PROPS = [
    [_nom("PER", 1), _num("€", 0)],  # 0 : Paul, 100 €
    [_nom("PER", 3), _num("€", 1)],  # 1 : 40 €
    [_num("%", 2)],  # 2 : 10 %
    [_date(3)],  # 3 : 2025-03-01
    [_date(4)],  # 4 : 2025-03-11
    [_num("€", 5)],  # 5 : 0 €
    [_nom("ORG", 300)],  # 6 : négative
    [_nom("PER", 2)],  # 7 : dépend de 6
    *([_num("€", v)] for v in range(6, 10)),  # 8 à 11 : 5, 6, 7, 8 €
]
VALEURS = {0: "100", 1: "40", 2: "10", 3: "2025-03-01", 4: "2025-03-11", 5: "0", 6: "5", 7: "6",
           8: "7", 9: "8"}  # fmt: skip
V = frozenset({"a", "payé", "le", "montant", ".", "ne", "pas"})


def _ctx(relations_noms=(), vocabulaire=V):
    ex = Exemple.model_validate(
        {
            "id": "t", "origine": "test", "langue": "fr", "historique": [],
            "question": _texte([_nom("PER", 1), _nom("PER", 2)], "et ?"),
            "propositions": [
                dict(_texte(m, "ne paie pas" if k == 6 else "a payé"), local=k, prop_id=100 + k,
                     piece=0, type_piece="RAPPORT", rang=0, ocr_bas=False, citee_avant=False)
                for k, m in enumerate(PROPS)
            ],
            "relations_noms": list(relations_noms),
            "relations_props": [[0, 1, "CONFLIT"], [7, 6, "DEPEND_DE"]],
            "cible": [], "justificatives": [],
        }
    )  # fmt: skip
    return Contexte.depuis_exemple(ex, VALEURS, NEGATION, vocabulaire)


def _apres(suite, ctx=None, cfg=CFG, synthese=False):
    a = Automate(ctx or _ctx(), cfg, synthese=synthese)
    for pas in suite:
        a.avancer(pas)
    return a.autorises()


def test_lexique():
    assert len(LEXIQUE) == 25 and len(LEXIQUE_COMPLET) == 30
    assert len(set(LEXIQUE_COMPLET)) == 30


def test_algebre_des_unites():
    eur = lambda v: Valeur("€", Decimal(v))  # noqa: E731
    d = lambda s: Valeur("date", date.fromisoformat(s), "JOUR")  # noqa: E731
    assert appliquer("+", eur("1.5"), eur("2")) == eur("3.5")
    assert appliquer("MIN", eur("1"), eur("2")) == eur("1")
    assert appliquer("+", eur("1"), Valeur("km", Decimal(1))) is None
    assert appliquer("−", d("2025-03-11"), d("2025-03-01")) == Valeur("jour", Decimal(10))
    assert appliquer("+", d("2025-03-01"), Valeur("jour", Decimal(10))) == d("2025-03-11")
    assert appliquer("−", d("2025-03-11"), Valeur("jour", Decimal(10))) == d("2025-03-01")
    assert appliquer("+", d("2025-03-01"), d("2025-03-01")) is None
    assert appliquer("×", eur("200"), Valeur("%", Decimal("0.1"))) == eur("20.0")
    assert appliquer("×", Valeur("", Decimal(3)), eur("2")) == eur("6")
    assert appliquer("×", eur("2"), eur("2")) is None
    assert appliquer("÷", eur("10"), eur("4")) == Valeur("", Decimal("2.5"))
    assert appliquer("÷", eur("10"), Valeur("%", Decimal("0.5"))) == eur("20")
    assert appliquer("÷", eur("10"), eur("0")) is None  # le masque connaît les valeurs
    assert appliquer("÷", eur("10"), Valeur("km", Decimal(2))) is None
    mois = Valeur("date", "2025-03", "MOIS")
    assert appliquer("−", mois, d("2025-03-01")) is None


def test_debut():
    a = _apres([])
    assert {"ABSTENTION", "CONFLIT", "SAME", "ASK_SAME", "NOTE_SAME", "NOTE_DIFF"} <= a
    assert {f"P:{k}" for k in range(8)} <= a
    assert not a & ({"FIN", "CALCUL", *CONNECTEURS, *NAVIGATION})  # CALCUL : rien de cité
    assert _apres(["ABSTENTION"]) == {"FIN"}


def test_segments_et_connecteurs():
    assert _apres(["P:0"]) == {"FIN", *CONNECTEURS}
    a = _apres(["P:0", "ET"])
    assert "FIN" not in a and "ABSTENTION" not in a and "P:0" not in a and "P:1" in a
    with pytest.raises(ValueError):
        _apres(["P:0", "ET", "P:0"])


def test_calcul():
    a = _apres(["P:0", "ET", "P:1", "DONC"])
    assert "CALCUL" in a
    a = _apres(["P:0", "ET", "P:1", "DONC", "CALCUL"])
    assert a == {"N:0.1", "N:1.1"}  # nombres des propositions citées seulement
    assert "FIN_CALCUL" not in _apres(["P:0", "ET", "P:1", "DONC", "CALCUL", "N:0.1"])
    assert "N:0.1" in _apres(["P:0", "ET", "P:1", "DONC", "CALCUL", "N:0.1"])  # réemploi permis
    a = _apres(["P:0", "ET", "P:1", "DONC", "CALCUL", "N:0.1", "N:1.1"])
    assert {"+", "−", "MIN", "MAX", "÷"} <= a and "×" not in a and "FIN_CALCUL" not in a
    a = _apres(["P:0", "ET", "P:1", "DONC", "CALCUL", "N:0.1", "N:1.1", "−"])
    assert "FIN_CALCUL" in a
    assert _apres(["P:0", "ET", "P:1", "DONC", "CALCUL", "N:0.1", "N:1.1", "−", "FIN_CALCUL"]) == {
        "FIN", *CONNECTEURS}  # fmt: skip


def test_calcul_valeurs_et_unites():
    a = _apres(["P:0", "ET", "P:5", "DONC", "CALCUL", "N:0.1", "N:5.0"])
    assert "÷" not in a and "+" in a  # diviseur nul
    a = _apres(["P:0", "ET", "P:2", "DONC", "CALCUL", "N:0.1", "N:2.0"])
    assert "×" in a and "+" not in a
    a = _apres(["P:3", "ET", "P:4", "DONC", "CALCUL", "N:4.0", "N:3.0"])
    assert "−" in a and "+" not in a
    # Aucune impasse : pas de CALCUL sans deux nombres cités compatibles.
    assert "CALCUL" not in _apres(["P:0", "ET", "P:3", "DONC"])


def test_calcul_douze_pas():
    """Sept nombres cités ; après 11 pas, un nombre de plus demanderait 13 pas."""
    suite = ["P:0", "ET", "P:1", "ET", "P:5"]
    for k in range(8, 12):
        suite += ["ET", f"P:{k}"]
    suite += ["DONC", "CALCUL", "N:0.1", "N:1.1", "+"]
    for k in (5, 8, 9, 10):
        suite += [f"N:{k}.0", "+"]
    assert len(suite) - suite.index("CALCUL") - 1 == 11
    assert _apres(suite) == {"FIN_CALCUL"}
    assert "N:11.0" in _apres(suite[:-2])  # 9 pas : encore la place


def test_conflit():
    a = _apres(["CONFLIT"])
    assert {"P:0", "P:1", "SANS_PREUVE"} <= a and "P:2" not in a and "DECLARATION" not in a
    assert _apres(["CONFLIT", "P:0"]) == {"P:1"}
    assert _apres(["CONFLIT", "P:0", "P:1"]) == {"FIN_CONFLIT"}
    assert "P:1" not in _apres(["CONFLIT", "P:0", "P:1", "FIN_CONFLIT", "ET"])


def test_conflit_sans_preuve():
    assert "FIN_CONFLIT" not in _apres(["CONFLIT", "SANS_PREUVE", "P:2"])
    a = _apres(["CONFLIT", "SANS_PREUVE", "P:2", "P:3"])
    assert "FIN_CONFLIT" in a and "P:2" not in a and "P:4" in a
    assert _apres(["CONFLIT", "SANS_PREUVE", "P:2", "P:3", "P:4", "P:5"]) == {"FIN_CONFLIT"}


def test_conflit_declaration():
    ctx = _ctx([[1, 3, "DIFFERENT_UTILISATEUR"]])
    assert "DECLARATION" in _apres(["CONFLIT"], ctx)
    a = _apres(["CONFLIT", "DECLARATION"], ctx)
    assert {"M:q.0", "M:0.0", "M:1.0"} <= a and "M:7.0" not in a
    assert _apres(["CONFLIT", "DECLARATION", "M:q.0"], ctx) == {"M:1.0"}
    a = _apres(["CONFLIT", "DECLARATION", "M:q.0", "M:1.0"], ctx)
    assert a == {f"P:{k}" for k in range(len(PROPS))}
    assert "FIN_CONFLIT" in _apres(["CONFLIT", "DECLARATION", "M:q.0", "M:1.0", "P:4"], ctx)


def test_same():
    ctx = _ctx([[1, 3, "DIFFERENT_UTILISATEUR"]])
    a = _apres(["SAME", "M:q.0"], ctx)
    assert a == {"M:q.1", "M:7.0"}  # même type, autre nom, sans contrainte DIFFERENT
    assert _apres(["SAME", "M:q.0", "M:7.0"], ctx) == {"P:0", "P:7", "SANS_PREUVE"}
    assert "P:0" not in _apres(["SAME", "M:q.0", "M:7.0", "P:0", "ET"], ctx)  # preuve citée
    assert "CALCUL" in _apres(["SAME", "M:q.0", "M:7.0", "P:0", "ET", "P:1", "DONC"], ctx)
    assert _apres(["ASK_SAME", "M:q.0", "M:7.0"], ctx) == {"FIN", *CONNECTEURS}
    assert "M:6.0" not in _apres(["SAME"], ctx)  # ORG seul de son type


def test_note():
    assert _apres(["NOTE_SAME"]) == {"M:q.0", "M:q.1"}
    assert _apres(["NOTE_DIFF", "M:q.0"]) == {"M:q.1"}


def test_budget_de_pas():
    cfg = CFG.model_copy(update={"pas_max": 3})
    assert _apres(["P:0"], cfg=cfg) == {"FIN"}
    assert "CALCUL" not in _apres([], cfg=cfg) and "SAME" not in _apres([], cfg=cfg)


def test_synthese():
    assert "SYNTHESE" not in _apres(["P:0"])  # mode citation
    assert "SYNTHESE" in _apres(["P:0"], synthese=True)
    assert _apres(["P:0", "SYNTHESE"], synthese=True) == {"SOURCES"}
    assert _apres(["P:0", "SYNTHESE", "SOURCES"], synthese=True) == {"P:0"}
    a = _apres(["P:0", "SYNTHESE", "SOURCES", "P:0"], synthese=True)
    assert a == {"DEBUT"}
    debut = ["P:0", "SYNTHESE", "SOURCES", "P:0", "DEBUT"]
    a = _apres(debut, synthese=True)
    assert {"W:a", "W:A", "M:0.0", "N:0.1", "W:."} <= a
    assert not a & {"FIN_PHRASE", "W:ne", "W:pas", "M:q.0", "N:1.1", "CALCUL"}
    a = _apres([*debut, "W:le"], synthese=True)
    assert "W:Le" not in a and "W:le" in a  # majuscule : premier mot seulement
    a = _apres([*debut, "W:le", "N:0.1"], synthese=True)
    assert "FIN_PHRASE" in a
    a = _apres([*debut, "W:le", "N:0.1", "FIN_PHRASE"], synthese=True)
    assert a == {"SOURCES", "FIN_SYNTHESE"}
    assert _apres([*debut, "W:le", "N:0.1", "FIN_PHRASE", "FIN_SYNTHESE"], synthese=True) == {
        "FIN"}  # fmt: skip


def test_synthese_dependances_et_negation():
    a = _apres(["P:7", "SYNTHESE", "SOURCES", "P:7", "DEBUT"], synthese=True)
    assert {"M:6.0", "M:7.0", "W:ne", "W:pas"} <= a  # P6 : dépendance de P7, négative


def test_synthese_limites():
    suite = ["P:0", "SYNTHESE"]
    for _ in range(CFG.phrases_max):
        suite += ["SOURCES", "P:0", "DEBUT", "M:0.0", "FIN_PHRASE"]
    assert _apres(suite, synthese=True) == {"FIN_SYNTHESE"}
    suite = ["P:0", "SYNTHESE", "SOURCES", "P:0", "DEBUT"] + ["W:le"] * CFG.mots_phrase
    a = _apres(suite, synthese=True)
    assert "W:le" not in a and "M:0.0" in a


def test_synthese_calcul_dans_les_sources():
    debut = ["P:0", "ET", "P:1", "SYNTHESE", "SOURCES", "P:0", "P:1", "DEBUT"]
    assert "CALCUL" in _apres(debut, synthese=True)
    assert _apres([*debut, "CALCUL"], synthese=True) == {"N:0.1", "N:1.1"}


@pytest.mark.parametrize("synthese", [False, True])
def test_decodages_aleatoires(synthese):
    ctx = _ctx([[1, 3, "DIFFERENT_UTILISATEUR"]])
    pas_max = CFG.pas_max_synthese if synthese else CFG.pas_max
    for graine in range(300):
        suite = decoder_au_hasard(ctx, CFG, graine, synthese=synthese)
        assert suite[-1] == "FIN" and len(suite) <= pas_max
        assert not set(suite) & set(NAVIGATION)
        assert accepter(ctx, suite, CFG, synthese=synthese)


def test_accepter():
    ctx = _ctx()
    assert accepter(ctx, ["P:0", "ET", "P:1", "FIN"], CFG)
    assert not accepter(ctx, ["P:0", "ET", "P:1"], CFG)  # pas fini
    assert not accepter(ctx, ["FIN"], CFG)
    assert not accepter(ctx, ["P:0", "OUVRIR", "FIN"], CFG)
