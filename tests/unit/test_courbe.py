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
