"""Chargeur de données du réglage fin (SPEC.md §12, « Exemples négatifs et difficiles » ; §13).

Test du §13 : chaque pas de référence est autorisé par son masque, calculé par l'automate
dans le chargeur, pour tous les genres d'exemples (normal, abstention, conflit injecté,
contrefactuel, contexte incomplet) et pour les sources synthétique et publiques.
"""

import re
import zlib

import pytest

from ccm.anonymize.encode import Vocabulaire
from ccm.config import load_config
from ccm.data import finqa, hotpot, negatives
from ccm.data.publics import Brut, stock_de
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.ner.detectors import Zone
from ccm.schema import Detecteur, MarqueNom, Relation, TypeNom
from ccm.train.chargeur import Chargeur, SourcePublique, SourceSynthetique, blocs_conflit

CFG = load_config("ingest")
GCFG = load_config("grammar")
SCFG = load_config("search")
WCFG = load_config("worldgen")
CHCFG = load_config("finetune").chargeur
TAILLE = 50_000
VOC = Vocabulaire(load_config("model_b_s"), CFG, TAILLE)
NOMS = re.compile(r"Ada Lovelace|Lovelace|Turing")


def decouper(t):  # tokenizer de test : un jeton par mot
    return [zlib.crc32(m.encode()) % TAILLE for m in t.split()]


def zones(t):
    return [Zone(*m.span(), TypeNom.PER, frozenset({Detecteur.GLINER})) for m in NOMS.finditer(t)]


def _chargeur(sources, jetons_max=None, **parts):
    return Chargeur(sources, CHCFG.model_copy(update=parts), CFG, SCFG, GCFG, VOC, decouper,
                    jetons_max)  # fmt: skip


def _dans_son_masque(t):
    e = t.encodage
    assert e.masque.shape == (len(t.exemple.cible), len(e.espace))
    assert e.masque[range(len(e.cible)), e.cible].all(), (t.exemple.id, t.genre, t.exemple.cible)
    assert [e.espace[i] for i in e.cible] == t.exemple.cible


@pytest.fixture(scope="module")
def synthetique():
    ds = []
    for i in (0, 1, 10):
        d = rediger_dossier(generer_monde(i, "entrainement", WCFG, frozenset()), WCFG)
        ds.append((d, poser_questions(d, WCFG)))
    return SourceSynthetique(ds, CFG)


# Questions publiques. FR_CONFLIT : même fait daté, une heure (conflit établi possible) ;
# FR_NOMBRE : un nombre sans date (contrefactuel sans conflit) ; le doublon pour l'abstention.
FR_CONFLIT = Brut("fr-c", "piaf", "fr", "À quelle heure Turing a-t-il signé ?",
                  [["Le 12 mars 2021, Turing a signé le contrat à 14 h 30.", "Le ciel était gris."],
                   ["Ada Lovelace a lu le texte.", "Elle a souri."]], [(0, 0)])  # fmt: skip
FR_NOMBRE = Brut("fr-n", "piaf", "fr", "Combien de livres Turing a-t-il achetés ?",
                 [["Turing a acheté 12 livres anciens au marché.", "Il pleuvait."],
                  ["Turing a acheté 12 livres anciens au marché."],
                  ["Ada Lovelace a lu le texte."]], [(0, 0)])  # fmt: skip


def _hotpot():
    return hotpot.brut_de({
        "id": "a1", "question": "Who worked with Turing?",
        "context": {"title": ["Turing", "Lovelace"],
                    "sentences": [[" Turing was born in 1912.", " "],
                                  ["Ada Lovelace wrote notes.", " She died."]]},
        "supporting_facts": {"title": ["Lovelace", "Turing"], "sent_id": [1, 0]},
    })  # fmt: skip


def _finqa(tmp_path):
    f = tmp_path / "t.json"
    f.write_text('[{"pre_text": ["Revenue rose .", "costs were 500 in total ."], "post_text": [],'
                 ' "table": [["item", "2008", "2007"], ["sales", "$ 5,829", "$ 5,735"]],'
                 ' "qa": {"question": "What is the change?", "program": "subtract(5829, 5735)",'
                 ' "gold_inds": {"table_1": "sales"}}}]')  # fmt: skip
    return finqa.lire(f)[0][0]


@pytest.fixture(scope="module")
def publiques(tmp_path_factory):
    squad = Brut("squad-q", "squad", "en", "Where did Turing go?",
                 [["Turing was born.", "He studied."]], abstention=True)  # fmt: skip
    return {
        "hotpot": SourcePublique([_hotpot()], zones, CFG),
        "fquad_piaf": SourcePublique([FR_CONFLIT, FR_NOMBRE], zones, CFG),
        "finqa": SourcePublique([_finqa(tmp_path_factory.mktemp("finqa"))], zones, CFG),
        "squad": SourcePublique([squad], zones, CFG),
    }


# --- Test du §13 ---------------------------------------------------------------------


def test_chaque_pas_de_reference_dans_son_masque_synthetique(synthetique):
    ch = _chargeur({"synthetique": synthetique}, abstention=0.2, conflit_injecte=0.3,
                   contrefactuel=0.2, contexte_complet=0.9)  # fmt: skip
    tirages = list(ch.epoque(0, 150))
    for t in tirages:
        _dans_son_masque(t)
    genres = {t.genre for t in tirages}
    assert {"normal", "abstention", "conflit", "contrefactuel"} <= genres
    assert not [k for k in ch.bilan if k.startswith("sauté")], ch.bilan
    blocs = [t for t in tirages if t.genre == "conflit"]
    assert all("CONFLIT" in t.exemple.cible for t in blocs)


def test_chaque_pas_de_reference_dans_son_masque_publiques(publiques):
    ch = _chargeur(publiques, abstention=0.2, conflit_injecte=0.3, contrefactuel=0.2)
    tirages = list(ch.epoque(0, 80))
    assert len(tirages) == 80, ch.bilan
    for t in tirages:
        _dans_son_masque(t)
    assert {t.source for t in tirages} == set(publiques)
    calculs = [t for t in tirages if t.source == "finqa" and t.genre == "normal"]
    assert calculs and all("CALCUL" in t.exemple.cible for t in calculs)


# --- Mélange pondéré -----------------------------------------------------------------


def test_melange_pondere(publiques):
    ch = _chargeur(publiques)
    assert ch.absentes == ["droit", "synthetique"]
    poids = {"hotpot": 0.20, "fquad_piaf": 0.15, "finqa": 0.05, "squad": 0.05}
    parts = ch.parts(1000)
    assert sum(parts.values()) == 1000
    for s, w in poids.items():  # renormalisés sur les sources présentes
        assert abs(parts[s] - 1000 * w / 0.45) <= 1
    plan = ch.plan(0, 1000)
    assert plan == ch.plan(0, 1000) and plan != ch.plan(1, 1000)
    assert sorted(plan) != plan  # places mélangées
    for s, k in parts.items():
        assert sum(1 for x, _ in plan if x == s) == k


# --- Indices, abstention, conflit, contrefactuel, contexte réel -------------------------


def _noms(t):
    return [m.nom for p in (t.exemple.question, *t.exemple.propositions) for m in p.marques
            if isinstance(m, MarqueNom)]  # fmt: skip


def test_indices_tires_a_chaque_epoque(publiques):
    ch = _chargeur(publiques, abstention=0, conflit_injecte=0, contrefactuel=0)
    a, b = ch.exemple("hotpot", 0, 0, 0), ch.exemple("hotpot", 0, 1, 0)
    assert a.exemple.cible == b.exemple.cible and _noms(a) != _noms(b)
    assert _noms(a) == _noms(ch.exemple("hotpot", 0, 0, 0))  # même graine, mêmes indices
    # Même structure : l'égalité des noms est gardée.
    paires = lambda t: {(i, j) for i, x in enumerate(_noms(t)) for j, y in enumerate(_noms(t))  # noqa: E731
                        if x == y}  # fmt: skip
    assert paires(a) == paires(b)


def test_abstention_retire_justificatives_et_doublons(publiques):
    con, ids, _ = stock_de(FR_NOMBRE, zones, CFG)
    j, doublon = ids[0][0], ids[1][0]
    assert negatives.gardes(con)[doublon] == j
    assert negatives.retirer(con, [j]) == {j, doublon}
    assert not con.execute(
        f"SELECT 1 FROM proposition WHERE prop_id IN ({j}, {doublon})"
    ).fetchone()
    ch = _chargeur(publiques, abstention=1.0)
    t = ch.exemple("fquad_piaf", 1, 0, 0)
    assert t.genre == "abstention" and t.exemple.cible == ["ABSTENTION", "FIN"]
    rendues = {p.prop_id for p in t.exemple.propositions}  # stock refait : mêmes prop_ids
    assert rendues and not rendues & {j, doublon}
    _dans_son_masque(t)


def test_conflit_injecte(publiques):
    ch = _chargeur(publiques, abstention=0, conflit_injecte=1.0)
    t = ch.exemple("fquad_piaf", 0, 0, 0)
    assert t.genre == "conflit" and t.repli is None, t.repli
    c = t.exemple.cible
    assert c[0] == "CONFLIT" and c[3] == "FIN_CONFLIT" and c[-1] == "FIN"
    a, b = (int(p[2:]) for p in c[1:3])
    props = t.exemple.propositions
    assert props[a].rang != props[b].rang  # une nouvelle pièce d'un autre rang
    assert (a, b, Relation.CONFLIT) in t.exemple.relations_props  # trouvé par l'ingestion
    _dans_son_masque(t)


def test_conflit_non_trouve_repli_normal(publiques):
    ch = _chargeur(publiques, abstention=0, conflit_injecte=1.0)
    t = ch.exemple("fquad_piaf", 1, 0, 0)  # aucune date : pas de conflit établi possible
    assert t.genre == "normal" and t.repli.startswith("conflit")
    assert "CONFLIT" not in t.exemple.cible


def test_contrefactuel(publiques):
    con, ids, _ = stock_de(FR_NOMBRE, zones, CFG)
    j = ids[0][0]
    avant = con.execute("SELECT texte FROM proposition WHERE prop_id = ?", (j,)).fetchone()[0]
    rng = __import__("random").Random(0)
    assert negatives.contrefactuel(con, j, "fr", CFG, rng, 8)
    texte, valeur = con.execute("SELECT p.texte, n.valeur FROM proposition p JOIN nombre n "
                                "USING (prop_id) WHERE prop_id = ?", (j,)).fetchone()  # fmt: skip
    assert texte != avant and valeur != "12" and len(texte) == len(avant)
    assert texte.replace(valeur, "12") == avant
    habituelle = con.execute("SELECT p.texte FROM proposition p JOIN piece pc USING (piece_id) "
                             "WHERE pc.piece_id LIKE '%~habituelle'").fetchone()  # fmt: skip
    assert habituelle == (avant,)
    ch = _chargeur(publiques, abstention=0, conflit_injecte=0, contrefactuel=1.0)
    t = ch.exemple("fquad_piaf", 1, 0, 0)
    assert t.genre == "contrefactuel" and t.exemple.cible == [f"P:{t.exemple.justificatives[0]}",
                                                              "FIN"]  # fmt: skip
    _dans_son_masque(t)


def test_contexte_reel_incomplet(publiques):
    # Budget de 12 jetons : la recherche ne rend pas toutes les justificatives de HotpotQA.
    sans = _chargeur(publiques, jetons_max=12, abstention=0, contexte_complet=0.0)
    t = sans.exemple("hotpot", 0, 0, 0)
    assert t.genre == "abstention_contexte" and t.exemple.cible == ["ABSTENTION", "FIN"]
    _dans_son_masque(t)
    avec = _chargeur(publiques, jetons_max=12, abstention=0, contexte_complet=1.0)
    t = avec.exemple("hotpot", 0, 0, 0)
    assert t.genre == "normal" and len(t.exemple.justificatives) == 2
    assert t.exemple.cible == ["P:" + str(t.exemple.justificatives[0]), "ET",
                               "P:" + str(t.exemple.justificatives[1]), "FIN"]  # fmt: skip
    _dans_son_masque(t)


def test_blocs_conflit_seulement_en_debut_de_segment(publiques):
    t = _chargeur(publiques, abstention=0, conflit_injecte=1.0).exemple("fquad_piaf", 0, 0, 0)
    a, b = (int(p[2:]) for p in t.exemple.cible[1:3])
    ex = t.exemple
    assert blocs_conflit(ex, [f"P:{a}", "FIN"]) == ["CONFLIT", f"P:{a}", f"P:{b}", "FIN_CONFLIT",
                                                     "FIN"]  # fmt: skip
    assert blocs_conflit(ex, [f"P:{a}", "ET", f"P:{b}", "FIN"]) == [f"P:{a}", "ET", f"P:{b}", "FIN"]
