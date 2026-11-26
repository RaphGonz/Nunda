"""Courbes de perte (`ccm.train.courbe`) : tranches de 50 pas, débuts de nuit, page remplie."""

from ccm.train.courbe import TRANCHE, donnees, page


def _lignes():
    out = [{"etape": "reprise", "pas": 0}]
    out += [
        {"etape": "pas", "pas": i, "perte": 2.0, "sources": {"hotpot": 1.0}} for i in range(120)
    ]
    out += [{"etape": "arret", "pas": 120}, {"etape": "reprise", "pas": 120},
            {"etape": "reprise", "pas": 120}]  # fmt: skip
    return out + [{"etape": "pas", "pas": i, "perte": 1.0, "sources": {}} for i in range(120, 150)]


def test_donnees():
    d = donnees(_lignes(), 300)
    assert d["pas"] == [TRANCHE, 2 * TRANCHE, 3 * TRANCHE]
    assert d["total"] == [2.0, 2.0, 1.4]  # dernière tranche : 20 pas à 2, 30 à 1
    assert d["hotpot"][0] == 1.0 and d["synthetique"] == [None] * 3
    assert d["nuits"] == [0, 120]


def test_page_remplie():
    texte = page(_lignes(), 300)
    assert "__" not in texte.replace("__claude", "")
    assert "150 / 300" in texte


def test_sessions_et_sections():
    from ccm.train.courbe import comparaison_html, exemples_html

    assert donnees(_lignes(), 300, [0])["nuits"] == [0]
    tot = {"f1": 0.9, "exactes": 0.8, "abstention": 1.0, "abstention_a_tort": None}
    c = {m: {"hors_limite": 0, "sources": {"synthetique": tot, "hotpot": tot}}
         for m in ("A0", "A1", "B")}  # fmt: skip
    c["seuil"] = {"rapport": 1.0, "passe": True}
    ex = [{"source": "hotpot", "n_propositions": 3, "question": "Qui <a> ?", "ref": ["P:1", "FIN"],
           "propositions": [{"p": 1, "texte": "x", "justificative": True}],
           "suites": {"A0": ["P:1", "FIN"], "A1": ["P:1", "FIN"], "B": ["P:1"]}}]  # fmt: skip
    texte = page(_lignes(), 300, "b-fin", None, comparaison_html(c) + exemples_html(ex))
    assert "Perte d'entraînement de B" in texte and "100,0 %</b> de A1 : atteint" in texte
    assert "Qui &lt;a&gt; ?" in texte and "__" not in texte.replace("__claude", "")
    assert comparaison_html(None) == exemples_html(None) == ""
