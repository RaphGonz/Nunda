import random

from ccm.data.questions import fenetre_decision

PHRASE = "x" * 150


def test_fenetre_de_phrases_consecutives_sans_personne():
    props = [(i, "PHRASE", PHRASE) for i in range(10)]
    props[5] = (5, "PHRASE", "Maître Dupont, avocat au barreau.")
    idx = fenetre_decision(props, random.Random(0))
    assert 3 <= len(idx) <= 5 and 5 not in idx
    assert idx == list(range(idx[0], idx[-1] + 1))


def test_pas_de_fenetre_si_trop_court_ou_autre_genre():
    assert fenetre_decision([(0, "PHRASE", PHRASE), (1, "PARTIE", PHRASE)], random.Random(0)) == []
    props = [(i, "EN_TETE" if i % 2 else "PHRASE", PHRASE) for i in range(10)]
    assert fenetre_decision(props, random.Random(0)) == []
