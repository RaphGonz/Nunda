import re
from collections import Counter, defaultdict

import pytest

from ccm.config import load_config
from ccm.data.worldgen.monde import cle, generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import (
    GENRE_ATTRIBUT,
    TYPES,
    Element,
    Phrase,
    controler_phrase,
    controler_questions,
    gabarits_questions,
    mots_interdits,
    poser_questions,
)

CFG = load_config("worldgen")
Q = CFG.questions
GRAINE = {"entrainement": 0, "test": 2_000_000}


def dossier(i, reservoir="entrainement"):
    return rediger_dossier(generer_monde(GRAINE[reservoir] + i, reservoir, CFG, frozenset()), CFG)


@pytest.fixture(scope="module")
def echantillon():
    out = {}
    for res in GRAINE:
        ds = [dossier(i, res) for i in range(150)]
        out[res] = [(d, poser_questions(d, CFG)) for d in ds]
    return out


def lignes(d):
    return {f"{p.id}:{i}": x for p in d.pieces for i, x in enumerate(p.lignes)}


@pytest.mark.parametrize("reservoir", list(GRAINE))
def test_controle_des_questions(echantillon, reservoir):
    """Lignes et faits existants, ancrage, calculs, conflits, règles du masque (§10 bis)."""
    for d, qs in echantillon[reservoir]:
        assert controler_questions(d, qs) == []


def test_environ_quarante_questions_par_dossier(echantillon):
    for res in GRAINE:
        n = [len(qs) for _, qs in echantillon[res]]
        assert abs(sum(n) / len(n) - Q.par_dossier) <= 1
        assert min(n) >= 25
        for _, qs in echantillon[res]:
            assert len({q.id for q in qs}) == len(qs)
            textes = [(tuple(h.texte for h in q.historique), q.message.texte) for q in qs]
            assert len(set(textes)) == len(textes)


def test_parts_des_types(echantillon):
    """Parts de §12. Le conflit vient des seuls dossiers à versions contradictoires ;
    les autres types gardent leurs proportions entre eux (à 2 points près)."""
    qs = [q for _, x in echantillon["entrainement"] for q in x]
    n = Counter(q.type for q in qs)
    assert set(n) == set(TYPES)
    hors_conflit = len(qs) - n["CONFLIT"]
    total = sum(v for t, v in Q.parts.items() if t != "CONFLIT")
    for t, v in Q.parts.items():
        if t != "CONFLIT":
            assert abs(n[t] / hors_conflit - v / total) < 0.02, t
    # Une version contradictoire qui nomme les témoins autrement que toutes les autres
    # lignes (initiales seules, par exemple) n'a pas de question de conflit sans identité.
    avec = [
        any(q.type == "CONFLIT" for q in x) for d, x in echantillon["entrainement"] if d.conflit
    ]
    assert sum(avec) >= 0.9 * len(avec)
    assert all(
        q.type != "CONFLIT" for d, x in echantillon["entrainement"] if not d.conflit for q in x
    )
    sous = Counter((q.type, q.sous_type) for q in qs)
    for s in ("SUITE", "NOTE_SAME", "NOTE_DIFF", "DECLARATION_FAUSSE", "ASK_SAME"):
        assert sous[("DIALOGUE", s)] > 0, s
    for s in ("SOMME", "SOMME_UNE", "ECART", "DUREE", "MIN", "MAX"):
        assert sous[("CALCUL", s)] > 0, s
    etapes = Counter(len(q.etapes) for q in qs if q.type == "PLUSIEURS_ETAPES")
    assert set(etapes) == {2, 3, 4}
    preuves = Counter(q.identites[0].preuve is not None for q in qs if q.type == "IDENTITE")
    assert preuves[True] and preuves[False]


def test_meme_graine_memes_questions():
    for i in (0, 7):
        d = dossier(i)
        assert poser_questions(d, CFG) == poser_questions(dossier(i), CFG)


def test_verite_par_type(echantillon):
    for d, qs in echantillon["entrainement"]:
        lg = lignes(d)
        for q in qs:
            if q.type == "FAIT_SIMPLE":
                (et,) = q.etapes
                assert all(
                    any(f.genre == GENRE_ATTRIBUT[q.sous_type] for f in lg[r].faits)
                    for r in et.lignes
                )
            if q.type == "FAIT_ABSENT":
                assert q.abstention and not q.etapes and not q.synthese
            if q.type == "CONFLIT":
                assert [e.role for e in q.etapes] == ["CONFLIT", "CONFLIT"]
                assert d.conflit.evenement == lg[q.etapes[0].lignes[0]].evenement
            if q.type == "IDENTITE":
                (idt,) = q.identites
                nom_q = cle(q.message.faits[idt.question].surface)
                ligne, _, i = idt.fait.rpartition(":")
                f = lg[ligne].faits[int(i)]
                assert f.entite == q.message.faits[idt.question].entite
                assert cle(f.surface) != nom_q
                if idt.preuve:
                    entites = [x.entite for x in lg[idt.preuve].faits if x.genre == "PER"]
                    assert entites.count(f.entite) >= 2
            if q.declaration:
                a, b = (q.message.faits[i] for i in q.declaration.faits)
                meme = a.entite == b.entite
                assert q.declaration.juste == (meme == (q.declaration.genre == "MEME"))
            if q.sous_type == "ASK_SAME":
                (f,) = q.message.faits[:1]
                assert f.entite is None and len(q.ambigus) >= 2
            if q.sous_type == "SUITE":
                assert q.historique[1].role == "MODELE" and not q.message.faits


@pytest.mark.parametrize("reservoir", list(GRAINE))
def test_formulations_de_la_synthese(reservoir):
    """§10 bis : au moins 5 formulations par type de relation ; chaque gabarit respecte
    les règles du masque (mots, pas de chiffre, de nombre, de négation, de nom courant)."""
    g = gabarits_questions(reservoir)["synthese"]
    interdits = mots_interdits()
    for relation, modeles in g.items():
        assert len(set(modeles)) >= 5, relation
        for m in modeles:
            texte = re.sub(r"[\[\]]", "", re.sub(r"\{\w+\}", "", m))
            ph = Phrase(
                relation=relation,
                gabarit="",
                sources=("P01:0",),
                elements=(Element(genre="MOTS", mots=texte), Element(genre="M", fait="P01:0:0")),
                texte="",
            )
            err = controler_phrase(ph, {"P01:0"}, {"P01:0": _LIGNE}, interdits)
            assert err == [], (m, err)


class _F:
    genre = "PER"


class _L:
    faits = (_F(),)


_LIGNE = _L()


def test_formulations_vues_dans_le_corpus(echantillon):
    for res in GRAINE:
        vues = defaultdict(set)
        for _, qs in echantillon[res]:
            for q in qs:
                for ph in q.synthese:
                    vues[ph.relation].add(ph.gabarit)
        relations = gabarits_questions(res)["synthese"]
        assert set(vues) == set(relations)
        for rel, gs in vues.items():
            assert len(gs) >= 5, (res, rel)


def test_gabarits_test_disjoints():
    """Aucun texte de question ni de synthèse commun aux jeux entrainement et test."""

    def textes(g):
        out = set()
        for v in g.values():
            if isinstance(v, dict):
                out |= textes(v)
            else:
                out |= set(v)
        return out

    a, b = (textes(gabarits_questions(r)) for r in GRAINE)
    assert not a & b
