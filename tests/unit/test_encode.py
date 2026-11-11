"""`anonymize.encode` (SPEC.md §8) : séquence, jetons spéciaux, tables d'indices, héritage
des indices par les pas de sortie. T2 sur l'encodage entier : `test_t2_anonymiseur.py`."""

import zlib
from pathlib import Path

import numpy as np
import pytest

from ccm.anonymize.encode import Vocabulaire, encode, masque_pas, tables_relations
from ccm.config import load_config
from ccm.data.worldgen.cibles import cible_de_reference, exemple_de_reference
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.eval.equivariance import stock_de_reference
from ccm.grammar.automaton import Automate, Contexte
from ccm.schema import LEXIQUE, LEXIQUE_SYNTHESE, Exemple, Proposition, Relation, TexteMarque

CFG = load_config("ingest")
GCFG = load_config("grammar")
WCFG = load_config("worldgen")
SPEC = Exemple.model_validate_json(
    (Path(__file__).parent.parent / "golden" / "exemple_spec.json").read_text(encoding="utf-8")
)
TAILLE = 0x110000  # tokenizer de test : un jeton par caractère


def _car(texte):
    return [ord(c) for c in texte]


def _voc(variante="model_b_s", taille=TAILLE, **maj):
    cfg = load_config(variante)
    return Vocabulaire(cfg.model_copy(update=maj), CFG, taille)


def _rendu(enc, voc):
    """Jetons spéciaux par leur nom ; caractères voisins réunis."""
    out, mot = [], ""
    for i in enc.input_ids.tolist():
        if i < voc.taille:
            mot += chr(i)
            continue
        if mot:
            out.append(mot)
            mot = ""
        out.append(voc.jetons[i - voc.taille])
    return out


def _num(valeur_id, rang=0, unite="€", grandeur=2, signe=1):
    return dict(genre="NUM", unite=unite, grandeur=grandeur, rang_valeur=rang,
                valeur_id=valeur_id, signe=signe)  # fmt: skip


def _nom(nom, type_="PER"):
    return dict(genre="NOM", type=type_, nom=nom)


def _prop(k, texte="Rien.", marques=(), **attrs):
    d = dict(local=k, prop_id=100 + k, piece=0, type_piece="AUTRE", rang=0, ocr_bas=False,
             citee_avant=False, texte=texte, marques=list(marques))  # fmt: skip
    return Proposition(**(d | attrs))


def _exemple(props, question=None, historique=(), cible=(), rel_noms=(), rel_props=()):
    return Exemple(
        id="x", origine="test", langue="fr",
        question=question or TexteMarque(texte="Quoi ?", marques=[]),
        historique=list(historique), propositions=list(props),
        relations_noms=list(rel_noms), relations_props=list(rel_props),
        cible=list(cible), justificatives=[],
    )  # fmt: skip


# --- Séquence ------------------------------------------------------------------------


def test_sequence_a0_exemple_de_la_spec():
    voc = _voc("model_a0")
    assert _rendu(encode(SPEC, voc, _car), voc) == [
        "[BOS]",
        "[Q]", "Avec qui ", "⟨PER_3⟩", " a-t-il signé le contrat ?", "[/Q]",
        "[REL]",
        "⟨PER_3⟩", "⟨R:INITIALES_DE⟩", "⟨PER_5⟩",
        "⟨PER_3⟩", "⟨R:ALIAS_DECLARE⟩", "⟨PER_5⟩",
        "[/REL]",
        "[P]", "⟨PIECE:PV_AUDITION⟩", "⟨RANG:1⟩",
        "⟨PER_5⟩", ", dit ", "⟨PER_3⟩", ", a signé le contrat avec ", "⟨ORG_9⟩", " le ",
        "⟨DATE_12⟩", ".", "[/P]",
        "[SORTIE]", "⟨PT:P⟩", "ET", "SAME", "⟨PT:M⟩", "⟨PT:M⟩", "⟨PT:P⟩", "FIN",
    ]  # fmt: skip


def test_a1_reservoir_sans_rel():
    voc = _voc("model_a1")
    r = _rendu(encode(SPEC, voc, _car), voc)
    assert "[REL]" not in r and "⟨R:ALIAS_DECLARE⟩" not in voc.jetons
    assert {"⟨PER_3⟩", "⟨ORG_9⟩", "⟨DATE_12⟩"} <= set(r)


def test_b_un_slot_par_type_sans_rel():
    voc = _voc("model_b_s")
    r = _rendu(encode(SPEC, voc, _car), voc)
    assert "[REL]" not in r
    assert r[2:5] == ["Avec qui ", "⟨PER⟩", " a-t-il signé le contrat ?"]
    assert {"⟨ORG⟩", "⟨DATE⟩"} <= set(r) and "⟨PER_3⟩" not in voc.jetons


def test_historique_du_plus_ancien_au_plus_recent():
    h = [TexteMarque(texte=t, marques=[]) for t in ("ancien", "moyen", "récent")]
    voc = _voc()
    r = _rendu(encode(_exemple([_prop(0)], historique=h), voc, _car), voc)
    assert r[:11] == ["[BOS]", "[H]", "ancien", "[/H]", "[H]", "moyen", "[/H]", "[H]", "récent",
                      "[/H]", "[Q]"]  # fmt: skip


def test_metadonnees_d_une_proposition():
    props = [
        _prop(0, type_piece="PV_AUDITION", rang=1, ocr_bas=True, citee_avant=True),
        _prop(1, type_piece="LOI", rang=4),
        _prop(2),
        _prop(3),
    ]
    rels = [(0, 1, Relation.CONFLIT), (2, 3, Relation.DEPEND_DE)]
    voc = _voc()
    r = _rendu(encode(_exemple(props, rel_props=rels), voc, _car), voc)
    lignes = " ".join(r).split("[P] ")[1:]
    assert lignes[0].startswith(
        "⟨PIECE:PV_AUDITION⟩ ⟨RANG:1⟩ [OCR_BAS] [CITEE_AVANT] [CONFLIT] Rien"
    )
    assert lignes[1].startswith("⟨PIECE:LOI⟩ ⟨RANG:4⟩ [CONFLIT] Rien")
    assert lignes[2].startswith("⟨PIECE:AUTRE⟩ ⟨RANG:0⟩ [DEPEND] Rien")  # a dépend de b
    assert lignes[3].startswith("⟨PIECE:AUTRE⟩ ⟨RANG:0⟩ Rien")


def test_jetons_speciaux_de_la_spec():
    a0, a1, b = _voc("model_a0"), _voc("model_a1"), _voc("model_b_s")
    for v in (a0, a1, b):
        assert len(set(v.jetons)) == len(v.jetons)
        assert {
            "[BOS]",
            "[H]",
            "[/H]",
            "[Q]",
            "[/Q]",
            "[P]",
            "[/P]",
            "[SORTIE]",
            "[MASK]",
            "[NOUVEAU]",
            "[OCR_BAS]",
            "[CITEE_AVANT]",
            "[CONFLIT]",
            "[DEPEND]",
        } <= set(v.jetons)
        assert {"⟨RANG:0⟩", "⟨RANG:4⟩", "⟨PT:P⟩", "⟨PT:N⟩", "⟨PT:M⟩"} <= set(v.jetons)
        assert sum(j.startswith("⟨PIECE:") for j in v.jetons) == 8
        assert sum(j.startswith("⟨RANG:") for j in v.jetons) == 5
        assert set(LEXIQUE + LEXIQUE_SYNTHESE) <= set(v.jetons)
    noms = ("PER", "ORG", "LIEU", "REF", "AUTRE")
    for v in (a0, a1):
        assert sum(j.startswith(tuple(f"⟨{t}_" for t in noms)) for j in v.jetons) == 1280
        assert {"⟨PER_0⟩", "⟨AUTRE_255⟩", "⟨NUM_255⟩", "⟨DATE_255⟩"} <= set(v.jetons)
    assert {f"⟨{t}⟩" for t in (*noms, "NUM", "DATE")} <= set(b.jetons)
    assert sum(j.startswith("⟨R:") for j in a0.jetons) == 10  # relations 2 à 14, par nom
    assert "⟨R:MEME_CHAINE⟩" not in a0.jetons
    assert not any(j.startswith("⟨R:") for j in (*a1.jetons, *b.jetons))
    # Les jetons nouveaux suivent ceux du tokenizer.
    assert a0.ids["[BOS]"] == TAILLE and min(a0.ids.values()) == TAILLE


# --- Tables d'indices ----------------------------------------------------------------


def _complet():
    """Douze propositions : la proposition 12 (locale 11) porte deux noms et deux nombres."""
    props = [_prop(k) for k in range(11)]
    props[1] = _prop(1, "⟦0⟧ paie ⟦1⟧.", [_nom(7), _num(40, rang=0)])
    props.append(
        _prop(
            11,
            "⟦0⟧ et ⟦1⟧ : ⟦2⟧ ou ⟦3⟧ ?",
            [
                _nom(7),
                _nom(300, "ORG"),
                _num(40, rang=0),
                dict(
                    genre="DATE",
                    unite="date",
                    grandeur=None,
                    rang_valeur=1,
                    valeur_id=9,
                    precision="MOIS",
                ),
            ],
        )  # fmt: skip
    )
    q = TexteMarque(
        texte="⟦0⟧ a ⟦1⟧ ?",
        marques=[_nom(300, "ORG"), _num(41, rang=1, grandeur=None, signe=0, unite="zzz")],
    )
    h = TexteMarque(texte="Et ⟦0⟧ ?", marques=[_nom(7)])
    cible = ["P:11", "ET", "SAME", "M:q.0", "M:11.1", "P:1", "DONC", "CALCUL", "N:11.2",
             "N:1.1", "+", "FIN_CALCUL", "FIN"]  # fmt: skip
    return _exemple(
        props,
        question=q,
        historique=[h],
        cible=cible,
        rel_noms=[(7, 300, Relation.PROCHE)],
        rel_props=[(0, 1, Relation.SUIVANTE)],
    )


def test_formes_et_segments():
    ex, voc = _complet(), _voc()
    e = encode(ex, voc, _car)
    t = len(e.input_ids)
    assert e.segment.shape == e.prop_idx.shape == e.name_idx.shape == e.val_idx.shape == (t,)
    assert e.num_attr.shape == (t, 4)
    r = [voc.jetons[i - voc.taille] if i >= voc.taille else None for i in e.input_ids.tolist()]
    deb_p, sortie = r.index("[P]"), r.index("[SORTIE]")
    assert set(e.segment[:deb_p]) == {0} and set(e.segment[deb_p:sortie]) == {1}
    assert set(e.segment[sortie:]) == {2}
    assert t - sortie == 1 + len(ex.cible)
    nn, pp = tables_relations(ex)
    assert np.array_equal(e.NN, nn) and np.array_equal(e.PP, pp)
    assert e.NN.shape == (3, 3) and e.PP.shape == (13, 13)


def test_prop_idx_et_fin_prop():
    ex, voc = _complet(), _voc()
    e = encode(ex, voc, _car)
    r = [voc.jetons[i - voc.taille] if i >= voc.taille else None for i in e.input_ids.tolist()]
    ouv = [i for i, x in enumerate(r) if x == "[P]"]
    fins = [i for i, x in enumerate(r) if x == "[/P]"]
    assert e.fin_prop.tolist() == fins and len(fins) == 12
    entree = e.segment < 2
    for k, (a, b) in enumerate(zip(ouv, fins, strict=True), 1):
        assert (e.prop_idx[a : b + 1] == k).all()
    assert (e.prop_idx[: ouv[0]] == 0).all()
    assert set(e.prop_idx[entree]) == set(range(13))


def test_mentions_nombres_et_noms_locaux():
    e = encode(_complet(), _voc(), _car)
    # Noms par première apparition : 7 (historique) → 1, 300 (question) → 2.
    assert e.name_idx[e.pos_mention].tolist() == [1, 2, 1, 1, 2]
    assert (e.name_idx[e.pos_nombre] == 0).all() and (e.val_idx[e.pos_mention] == 0).all()
    assert e.pos_mention.tolist() == sorted(e.pos_mention.tolist())
    # Les nombres pointables sont ceux des propositions (pas celui de la question).
    assert e.prop_nombre.tolist() == [2, 12, 12]
    assert e.prop_idx[e.pos_nombre].tolist() == [2, 12, 12]
    # Valeurs : 41 (question) → 1, 40 → 2, 9 → 3. MEME_NOMBRE : val_idx égaux.
    assert e.val_idx[e.pos_nombre].tolist() == [2, 2, 3]
    assert (e.val_idx[e.segment < 2] != 0).sum() == 4


def test_num_attr():
    e = encode(_complet(), _voc(), _car)
    n = np.flatnonzero(e.val_idx == 1)
    # Nombre de la question : unité inconnue → « autre » (17), zéro (1), rang 1 → 2, signe 0 → 2.
    assert e.num_attr[n[0]].tolist() == [17, 1, 2, 2]
    # € : 1re unité de la config ; 10² : grandeur − (−3) + 2 ; rang 0 → 1 ; signe + → 3.
    assert e.num_attr[e.pos_nombre[0]].tolist() == [1, 7, 1, 3]
    # Date : précision MOIS (17 + 2) ; ni grandeur ni signe ; rang 1 → 2.
    assert e.num_attr[e.pos_nombre[2]].tolist() == [19, 0, 2, 0]
    assert (e.num_attr[e.val_idx == 0] == 0).all()
    assert (e.num_attr[e.pos_mention] == 0).all()


# --- Héritage ------------------------------------------------------------------------


def test_heritage_des_indices():
    e = encode(_complet(), _voc(), _car)
    pos = range(len(e.input_ids) - e.cible.size, len(e.input_ids))
    # P:11 → proposition 12, rien d'autre.
    assert e.prop_idx[pos[0]] == 12 and e.name_idx[pos[0]] == 0 and e.val_idx[pos[0]] == 0
    # ET : aucun indice.
    assert e.prop_idx[pos[1]] == e.name_idx[pos[1]] == e.val_idx[pos[1]] == 0
    assert (e.num_attr[pos[1]] == 0).all()
    # M:q.0 → nom 2, pas de proposition ; M:11.1 → nom 2, proposition 12.
    assert e.name_idx[pos[3]] == 2 and e.prop_idx[pos[3]] == 0
    assert e.name_idx[pos[4]] == 2 and e.prop_idx[pos[4]] == 12
    # N:11.2 → valeur, attributs et proposition de la cible.
    n = e.pos_nombre[1]
    assert e.val_idx[pos[8]] == e.val_idx[n] and e.prop_idx[pos[8]] == 12
    assert (e.num_attr[pos[8]] == e.num_attr[n]).all() and e.name_idx[pos[8]] == 0
    # Mêmes indices sur toutes les tables, pour chaque pointeur.
    cibles = {0: e.fin_prop[11], 3: e.pos_mention[1], 4: e.pos_mention[4], 5: e.fin_prop[1],
              8: e.pos_nombre[1], 9: e.pos_nombre[0]}  # fmt: skip
    for k, c in cibles.items():
        p = pos[k]
        assert (e.prop_idx[p], e.name_idx[p], e.val_idx[p]) == (
            e.prop_idx[c], e.name_idx[c], e.val_idx[c])  # fmt: skip


def test_jetons_de_pointeur_et_de_lexique():
    voc = _voc()
    r = _rendu(encode(_complet(), voc, _car), voc)
    assert r[r.index("[SORTIE]") + 1 :] == [
        "⟨PT:P⟩", "ET", "SAME", "⟨PT:M⟩", "⟨PT:M⟩", "⟨PT:P⟩", "DONC", "CALCUL", "⟨PT:N⟩",
        "⟨PT:N⟩", "+", "FIN_CALCUL", "FIN",
    ]  # fmt: skip


# --- Espace des pas, cible, masque -----------------------------------------------------


def test_espace_et_cible():
    ex = _complet()
    e = encode(ex, _voc(), _car)
    l_, p, k, m = 30, 12, 3, 5
    assert len(e.espace) == l_ + p + k + m
    assert e.espace[:25] == LEXIQUE and e.espace[25:30] == LEXIQUE_SYNTHESE
    assert e.espace[l_] == "P:0" and e.espace[l_ + p] == "N:1.1"
    assert e.espace[l_ + p + k :] == ("M:h1.0", "M:q.0", "M:1.0", "M:11.0", "M:11.1")
    assert [e.espace[i] for i in e.cible] == ex.cible
    assert e.masque is None


def test_exemple_sans_cible():
    ex = _complet().model_copy(update=dict(cible=[]))
    voc = _voc()
    e = encode(ex, voc, _car)
    assert e.cible.shape == (0,)
    assert _rendu(e, voc)[-1] == "[SORTIE]"


def _reference(i):
    d = rediger_dossier(generer_monde(i, "entrainement", WCFG, frozenset()), WCFG)
    con = stock_de_reference(d, CFG)
    for q in poser_questions(d, WCFG):
        ex, valeurs = exemple_de_reference(d, q, con, CFG)
        ctx = Contexte.depuis_exemple(ex, valeurs, CFG.conflits.negation)
        cible = cible_de_reference(d, q, con, ex, CFG)
        yield ex.model_copy(update=dict(cible=cible)), ctx
    con.close()


def _mots(texte):
    return [zlib.crc32(m.encode()) % 32000 for m in texte.split()]


@pytest.mark.parametrize("i", [0, 10])
def test_masque_des_suites_de_reference(i):
    """Le masque de chaque pas est celui de l'automate, et la cible y est toujours (T10)."""
    voc = _voc("model_a0", taille=32000)
    for ex, ctx in _reference(i):
        e = encode(ex, voc, _mots, ctx=ctx, gcfg=GCFG)
        assert e.masque.shape == (len(ex.cible), len(e.espace)) and e.masque.dtype == bool
        assert e.masque[np.arange(len(ex.cible)), e.cible].all(), ex.id
        a = Automate(ctx, GCFG)
        for t, pas in enumerate(ex.cible):
            assert {e.espace[j] for j in np.flatnonzero(e.masque[t])} == set(a.autorises()), ex.id
            a.avancer(pas)
        # OUVRIR et RETOUR restent masqués en v1, comme les jetons de synthèse en citation.
        for j in ("OUVRIR", "RETOUR", "SYNTHESE", "SOURCES"):
            assert not e.masque[:, e.espace.index(j)].any()
        # Chaque pointeur du masque désigne une position de l'entrée, de la bonne famille.
        assert len(e.espace) == 30 + len(ex.propositions) + e.pos_nombre.size + e.pos_mention.size


def test_pas_interdit_refuse_au_masque():
    ctx = Contexte.depuis_exemple(SPEC, {12: "2024-05-01"}, ())
    e = encode(SPEC, _voc(), _car, ctx=ctx, gcfg=GCFG)  # l'exemple de §4 est accepté
    assert e.masque[np.arange(len(SPEC.cible)), e.cible].all()
    # Sans connecteur entre P:0 et SAME : refusé.
    sans_et = SPEC.model_copy(update=dict(cible=[p for p in SPEC.cible if p != "ET"]))
    with pytest.raises(ValueError, match="pas interdit"):
        encode(sans_et, _voc(), _car, ctx=ctx, gcfg=GCFG)


def test_masque_pas():
    espace = ("FIN", "ET", "P:0")
    assert masque_pas(espace, frozenset({"FIN", "P:0"})).tolist() == [True, False, True]
    with pytest.raises(ValueError, match="hors de l'espace"):
        masque_pas(espace, frozenset({"W:mot"}))


# --- Limites et troncature -------------------------------------------------------------


def test_limites():
    ex = _complet()
    for maj, motif in ((dict(t_max=10), "T ="), (dict(p_max=5), "P ="), (dict(s_max=5), "S =")):
        with pytest.raises(ValueError, match=motif):
            encode(ex, _voc(**maj), _car)


def test_rel_garde_les_premiers_par_ordre_d_apparition():
    """La troncature ne dépend pas des indices tirés au hasard."""
    rels = [(600, 7, Relation.PROCHE), (7, 300, Relation.PROCHE), (7, 300, Relation.INCOMPATIBLE)]
    p = _prop(0, "⟦0⟧ ⟦1⟧ ⟦2⟧", [_nom(7), _nom(300, "ORG"), _nom(600, "LIEU")])
    voc = _voc("model_a0", rel_max=2)
    r = _rendu(encode(_exemple([p], rel_noms=rels), voc, _car), voc)
    rel = r[r.index("[REL]") + 1 : r.index("[/REL]")]
    assert rel == ["⟨PER_7⟩", "⟨R:PROCHE⟩", "⟨ORG_44⟩", "⟨PER_7⟩", "⟨R:INCOMPATIBLE⟩", "⟨ORG_44⟩"]


def test_marqueurs_et_morceaux_au_tokenizer():
    """Le tokenizer ne reçoit que le texte entre les marqueurs, jamais un marqueur."""
    vus = []

    def decouper(t):
        vus.append(t)
        return []

    encode(SPEC, _voc(), decouper)
    assert vus == ["Avec qui ", " a-t-il signé le contrat ?", ", dit ",
                   ", a signé le contrat avec ", " le ", "."]  # fmt: skip


def test_deterministe_et_config():
    a, b = encode(_complet(), _voc(), _car), encode(_complet(), _voc(), _car)
    assert np.array_equal(a.input_ids, b.input_ids) and a.espace == b.espace
    for nom, var, t in (
        ("model_a0", "A0", 8192),
        ("model_a1", "A1", 8192),
        ("model_b_s", "B", 4096),
        ("model_b_m", "B", 4096),
    ):
        c = load_config(nom)
        assert (c.variante, c.t_max, c.p_max, c.s_max, c.rel_max) == (var, t, 150, 96, 200)
