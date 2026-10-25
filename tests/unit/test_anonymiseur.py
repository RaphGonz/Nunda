"""Anonymiseur (SPEC.md §6, §8) : analyse des noms, 24 relations, slots, table."""

import json

import pytest
from typer.testing import CliRunner

from ccm.anonymize.encode import tables_relations
from ccm.anonymize.exemple import Message, anonymiser
from ccm.anonymize.names import analyser, nom_famille, norme
from ccm.anonymize.relations import Nom, alias_declares, genre_titre, relations_noms
from ccm.anonymize.table import TableConversation
from ccm.anonymize.units import attributs
from ccm.cli import app
from ccm.config import load_config
from ccm.graph.store import ajouter_mentions, ajouter_nombres, ajouter_piece
from ccm.ingest.numbers import nombres
from ccm.ner import detectors
from ccm.schema import RELATION_IDS, Exemple, Relation, TypeArete, TypeNom, TypePiece, ouvrir_stock

CFG = load_config("ingest")
R = Relation


# --- Analyse d'un nom PER ---------------------------------------------------------


@pytest.mark.parametrize(
    "surface, famille, prenoms, initiales",
    [
        ("DUPONT Jean-Pierre", "dupont", ("jean", "pierre"), None),
        ("Jean-Pierre Dupont", "dupont", ("jean", "pierre"), None),
        ("DA SILVA Ana", "da silva", ("ana",), None),
        ("Jean de La Fontaine", "de la fontaine", ("jean",), None),
        ("J. Dupont", "dupont", ("j",), None),
        ("Dupont", "dupont", (), None),
        ("M. Dupont", "dupont", (), None),
        ("dupont", None, (), None),  # mot seul en minuscules : rôle inconnu
        ("JP", None, (), "JP"),
        ("J.-P.", None, (), "JP"),
        ("L.M.", None, (), "LM"),
    ],
)
def test_analyse_per(surface, famille, prenoms, initiales):
    a = analyser(surface, CFG.noms)
    assert (a.famille, a.prenoms, a.initiales) == (famille, prenoms, initiales)
    assert nom_famille(surface, CFG.noms) == famille


def test_norme_meme_nom():
    assert norme("Jean-Pierre DUPONT", CFG.noms) == norme("jean pierre  Dupont", CFG.noms)
    assert norme("M. Émile Zola", CFG.noms) == "emile zola"


# --- Les 24 relations ---------------------------------------------------------------


def noms(*xs):
    """("surface", type[, genres]) → liste de Nom (une surface par nom)."""
    out = []
    for x in xs:
        s, t, *g = x
        out.append(Nom(norme(s, CFG.noms), TypeNom(t), frozenset({s}), frozenset(g)))
    return out


def rel(*xs, declarees=()):
    return relations_noms(noms(*xs), CFG, declarees)


def test_identifiants_des_relations():
    ids = sorted(i for v in RELATION_IDS.values() for i in v)
    assert ids == list(range(1, 25))


def test_meme_famille_et_incompatible():
    assert rel(("Jean Dupont", "PER"), ("Marie Dupont", "PER")) == {
        (0, 1, R.MEME_FAMILLE),
        (0, 1, R.INCOMPATIBLE),
    }
    # Initiale, préfixe, prénom absent : compatibles.
    assert rel(("Jean Dupont", "PER"), ("J. Dupont", "PER")) == {(0, 1, R.MEME_FAMILLE)}
    assert rel(("Jean Dupont", "PER"), ("DUPONT Jean-Pierre", "PER")) == {
        (0, 1, R.MEME_FAMILLE),
        (0, 1, R.INCLUS_DANS),
    }
    # Jean et Jeanne : ni égaux, ni initiale, ni préfixe de mots.
    assert (0, 1, R.INCOMPATIBLE) in rel(("Jean Dupont", "PER"), ("Jeanne Dupont", "PER"))
    # Titres de genre différent devant deux noms de même famille.
    assert rel(("Dupont", "PER", "M"), ("Jeanne Dupont", "PER", "F")) == {
        (0, 1, R.MEME_FAMILLE),
        (0, 1, R.INCOMPATIBLE),
        (0, 1, R.INCLUS_DANS),
    }
    # Pas de famille commune : rien, même avec des titres de genre différent.
    assert rel(("Jean Martin", "PER", "M"), ("Jeanne Dupont", "PER", "F")) == set()
    # MEME_FAMILLE seulement entre deux PER.
    assert rel(("Dupont", "PER"), ("Dupont", "ORG")) == set()


def test_initiales_de():
    assert (0, 1, R.INITIALES_DE) in rel(("J.-P.", "PER"), ("Jean-Pierre Dupont", "PER"))
    assert (0, 1, R.INITIALES_DE) in rel(("JPD", "PER"), ("Jean-Pierre Dupont", "PER"))
    assert (1, 0, R.INITIALES_DE) in rel(("Jean-Pierre Dupont", "PER"), ("JP", "AUTRE"))
    assert not any(r == R.INITIALES_DE for *_, r in rel(("JM", "PER"), ("Jean Dupont", "PER")))


def test_proche():
    assert rel(("Durand", "PER"), ("Durant", "PER")) == {(0, 1, R.PROCHE)}
    assert rel(("Marc", "PER"), ("Marx", "PER")) == set()  # moins de 5 caractères
    assert (0, 1, R.PROCHE) in rel(("Catherine Durand", "PER"), ("Katherine Durant", "PER"))
    assert rel(("Durand", "PER"), ("Dirant", "PER")) == set()  # 2 écarts, moins de 10
    assert (0, 1, R.PROCHE) in rel(("Lefebvre", "PER"), ("Lefevbre", "PER"))  # transposition


def test_sigle_de():
    assert rel(("BNP", "ORG"), ("Banque Nationale de Paris", "ORG")) == {(0, 1, R.SIGLE_DE)}
    assert (1, 0, R.SIGLE_DE) in rel(("Banque nationale de Paris", "ORG"), ("B.N.P.", "ORG"))
    assert rel(("BNP", "ORG"), ("Banque de France", "ORG")) == set()


def test_inclus_dans():
    assert rel(("Alpha", "ORG"), ("société Alpha", "ORG")) == {(0, 1, R.INCLUS_DANS)}
    assert rel(("société Alpha", "ORG"), ("Alpha", "ORG")) == {(1, 0, R.INCLUS_DANS)}


def test_declarees():
    r = rel(
        ("Jean Dupont", "PER"),
        ("Le Belge", "PER"),
        ("Paul Roux", "PER"),
        declarees=[
            (1, 0, R.ALIAS_DECLARE),
            (0, 2, R.MEME_UTILISATEUR),
            (2, 1, R.DIFFERENT_UTILISATEUR),
            (2, 0, R.MEME_HYPOTHESE),
        ],
    )
    # Relations symétriques : une fois, plus petit indice d'abord.
    assert r == {
        (0, 1, R.ALIAS_DECLARE),
        (0, 2, R.MEME_UTILISATEUR),
        (1, 2, R.DIFFERENT_UTILISATEUR),
        (0, 2, R.MEME_HYPOTHESE),
    }


@pytest.mark.parametrize(
    "texte, a, b",
    [
        ("Jean Dupont, dit Le Belge, a signé.", "Jean Dupont", "Le Belge"),
        ("Marc Roux alias Bébert est entré.", "Marc Roux", "Bébert"),
        ("Paul Roux, surnommé Le Prof, est venu.", "Paul Roux", "Le Prof"),
        ("La société Alpha Conseil (ci-après « Alpha ») vend.", "Alpha Conseil", "Alpha"),
        ("Marie Durand épouse Martin est entendue.", "Marie Durand", "Martin"),
        ("Marie Martin, née Durand, déclare.", "Marie Martin", "Durand"),
    ],
)
def test_alias_declares(texte, a, b):
    ms = [
        (texte.index(a), texte.index(a) + len(a), 0),
        (texte.rindex(b), texte.rindex(b) + len(b), 1),
    ]
    assert alias_declares(texte, ms, CFG.noms) == {(0, 1)}


def test_pas_d_alias():
    texte = "Jean Dupont a vu Paul Roux, puis Marc Roux dit qu'il partait."
    ms = [(texte.index(s), texte.index(s) + len(s), k) for k, s in enumerate(
        ["Jean Dupont", "Paul Roux", "Marc Roux"])]  # fmt: skip
    assert alias_declares(texte, ms, CFG.noms) == set()


def test_genre_titre():
    t = "M. Dupont et Mme Durand ont vu Maître Roux et Dupont."
    assert genre_titre(t, t.index("Dupont"), CFG.noms) == "M"
    assert genre_titre(t, t.index("Durand"), CFG.noms) == "F"
    assert genre_titre(t, t.index("Roux"), CFG.noms) is None
    assert genre_titre(t, t.rindex("Dupont"), CFG.noms) is None


# --- Nombres et dates ---------------------------------------------------------------


def test_attributs_des_nombres():
    vals = [
        ("NUM", "1250.00", "€"),
        ("NUM", "30", "€"),
        ("NUM", "1250", "€"),  # même valeur que la première
        ("NUM", "0", "€"),
        ("NUM", "-2.5", "km"),
        ("DATE", "2024-12-07", "date"),
        ("DATE", "2024", "date"),
        ("NUM", "0.0004", "kg"),
        ("NUM", "5000000000000000", "€"),
    ]
    a = attributs(vals, CFG.anonymiseur)
    # (grandeur, rang dense parmi les valeurs de même unité, signe)
    assert a[0] == (3, 2, 1)
    assert a[1] == (1, 1, 1)
    assert a[2] == a[0]
    assert a[3] == (None, 0, 0)
    assert a[4] == (0, 0, -1)
    assert a[5] == (None, 1, None) and a[6] == (None, 0, None)
    assert a[7][0] == -3 and a[8][0] == 12  # bornes


def test_rang_borne():
    vals = [("NUM", str(k), "€") for k in range(1, 100)]
    assert [r for _, r, _ in attributs(vals, CFG.anonymiseur)][-1] == 63


# --- Table de la conversation -------------------------------------------------------


def test_table_tirage_sans_remise():
    t = TableConversation(graine=7, k=CFG.anonymiseur.reservoir)
    a = [t.nom(TypeNom.PER, f"n{k}") for k in range(256)]
    assert sorted(a) == list(range(256))
    assert t.nom(TypeNom.PER, "n3") == a[3]  # même nom, même indice
    assert t.nom(TypeNom.ORG, "n3") in range(256, 512)  # réservoir propre au type, bloc ORG
    with pytest.raises(ValueError):
        t.nom(TypeNom.PER, "n256")
    t2 = TableConversation(7, 256)
    assert [t2.nom(TypeNom.PER, f"n{k}") for k in range(5)] == a[:5]  # même graine
    v = t.valeur("€", "1250.00")
    assert t.valeur("€", "1250.00") == v and t.valeur("km", "1250.00") != v


# --- Exemple anonymisé --------------------------------------------------------------

TEXTES = [
    ("Jean Dupont, dit Le Belge, a payé 1 250 € à la société Alpha le 3 mai 2024.", "PHRASE"),
    ("Le Belge a reçu 300 € de Marie Dupont le 4 mai 2024.", "PHRASE"),
    ("JD a confirmé.", "PHRASE"),
]
NOMS = {"Jean Dupont": "PER", "Le Belge": "PER", "Alpha": "ORG", "Marie Dupont": "PER", "JD": "PER"}


def _mentions(texte):
    out = []
    for s, t in NOMS.items():
        k = texte.find(s)
        if k >= 0:
            out.append((k, k + len(s), s, norme(s, CFG.noms), t, "reference"))
    return sorted(out)


def _message(texte):
    zs = [(d, f, TypeNom(t)) for d, f, _, _, t, _ in _mentions(texte)]
    return Message(texte, tuple(zs), tuple(nombres(texte, CFG.nombres, [z[:2] for z in zs])))


@pytest.fixture
def stock():
    con = ouvrir_stock(":memory:")
    ids = ajouter_piece(
        con, "P01", "P01.pdf", "x", TypePiece.PV_AUDITION, 1, 1,
        [(1, t, g, 1.0) for t, g in TEXTES],
        [(0, 1, TypeArete.SUIVANTE), (1, 2, TypeArete.SUIVANTE), (2, 1, TypeArete.DEPEND_DE)],
    )  # fmt: skip
    for pid, (t, _) in zip(ids, TEXTES, strict=True):
        ms = _mentions(t)
        ajouter_mentions(con, pid, ms)
        ajouter_nombres(con, pid, nombres(t, CFG.nombres, [m[:2] for m in ms]))
    con.execute("INSERT INTO contrainte VALUES ('c1', 'MEME', 'jd', 'jean dupont', NULL, 'u', 'd')")
    return con, ids


def test_exemple_sans_nom(stock):
    con, ids = stock
    q = _message("Combien Jean Dupont a-t-il payé le 3 mai 2024 ?")
    ex = anonymiser(con, ids, q, TableConversation(0, 256), CFG, conv_id="c1")
    brut = ex.model_dump_json()
    for s in NOMS:
        assert s not in brut and norme(s, CFG.noms) not in brut.casefold()
    assert "1 250" not in brut and "mai" not in brut
    p0 = ex.propositions[0]
    assert p0.texte == "⟦0⟧, dit ⟦1⟧, a payé ⟦2⟧ à la société ⟦3⟧ le ⟦4⟧."
    assert [m.genre for m in p0.marques] == ["NOM", "NOM", "NUM", "NOM", "DATE"]
    assert ex.question.texte == "Combien ⟦0⟧ a-t-il payé le ⟦1⟧ ?"
    # Même nom, même indice ; même valeur et même unité, même valeur_id.
    assert ex.question.marques[0].nom == p0.marques[0].nom
    assert ex.question.marques[1].valeur_id == p0.marques[4].valeur_id
    assert ex.propositions[1].marques[0].nom == p0.marques[1].nom
    # Dates : rang chronologique ; montants : rang dense par unité.
    assert p0.marques[4].rang_valeur == 0 and ex.propositions[1].marques[3].rang_valeur == 1
    assert p0.marques[2].rang_valeur == 1 and ex.propositions[1].marques[1].rang_valeur == 0
    assert (p0.piece, p0.type_piece, p0.rang, p0.ocr_bas) == (0, TypePiece.PV_AUDITION, 1, False)

    nom = {m.nom: s for p in ex.propositions for m, s in zip(
        [m for m in p.marques if m.genre == "NOM"], _surfaces(p.local), strict=True)}  # fmt: skip
    rels = {(nom[a], nom[b], r) for a, b, r in ex.relations_noms}
    assert ("Le Belge", "Jean Dupont", R.ALIAS_DECLARE) in rels or (
        "Jean Dupont", "Le Belge", R.ALIAS_DECLARE) in rels  # fmt: skip
    assert ("JD", "Jean Dupont", R.INITIALES_DE) in rels
    assert {
        ("JD", "Jean Dupont", R.MEME_UTILISATEUR),
        ("Jean Dupont", "JD", R.MEME_UTILISATEUR),
    } & rels
    assert {frozenset((nom_a, nom_b)) for nom_a, nom_b, r in rels if r == R.MEME_FAMILLE} == {
        frozenset(("Jean Dupont", "Marie Dupont"))
    }
    assert set(ex.relations_props) == {
        (0, 1, R.SUIVANTE),
        (1, 2, R.SUIVANTE),
        (2, 1, R.DEPEND_DE),
    }
    json.loads(brut)


def _surfaces(k):
    t = TEXTES[k][0]
    return [s for _, _, s, *_ in _mentions(t)]


def test_hors_contexte_et_sans_conversation(stock):
    con, ids = stock
    ex = anonymiser(con, ids[1:2], _message("Et Paul ?"), TableConversation(0, 256), CFG)
    assert [p.prop_id for p in ex.propositions] == [ids[1]]
    assert not any(r in (R.MEME_UTILISATEUR,) for *_, r in ex.relations_noms)
    assert ex.relations_props == []
    assert ex.question.texte == "Et Paul ?"  # pas de mention fournie : texte inchangé


def test_meme_table_sur_deux_tours(stock):
    con, ids = stock
    t = TableConversation(3, 256)
    a = anonymiser(con, ids, _message("Qui est Le Belge ?"), t, CFG)
    b = anonymiser(con, ids[1:], _message("Et Marie Dupont ?"), t, CFG)
    assert a.propositions[1].marques[0].nom == b.propositions[0].marques[0].nom
    assert a.propositions[1].marques[2].nom == b.question.marques[0].nom


def test_tables_nn_pp(stock):
    con, ids = stock
    ex = anonymiser(con, ids, _message("Qui ?"), TableConversation(0, 256), CFG)
    nn, pp = tables_relations(ex)
    n = len({m.nom for p in ex.propositions for m in p.marques if m.genre == "NOM"})
    assert nn.shape == (n + 1, n + 1) and pp.shape == (4, 4)
    assert not nn[0].any() and not nn[:, 0].any() and not pp[0].any()
    bit = {r: [1 << (i - 1) for i in RELATION_IDS[r]] for r in RELATION_IDS}
    assert all(nn[i, i] & bit[R.MEME_CHAINE][0] for i in range(1, n + 1))
    # Numéros locaux par première apparition : Jean Dupont 1, Le Belge 2, Alpha 3, …, JD 5.
    assert nn[5, 1] & bit[R.INITIALES_DE][0] and nn[1, 5] & bit[R.INITIALES_DE][1]
    assert nn[1, 2] & bit[R.ALIAS_DECLARE][0] and nn[2, 1] & bit[R.ALIAS_DECLARE][0]
    assert pp[1, 2] & bit[R.SUIVANTE][0] and pp[2, 1] & bit[R.SUIVANTE][1]
    assert pp[3, 2] & bit[R.DEPEND_DE][0] and pp[2, 3] & bit[R.DEPEND_DE][1]
    assert all(pp[i, j] & bit[R.MEME_PIECE][0] for i in range(1, 4) for j in range(1, 4))
    assert all(pp[i, i] & bit[R.MEME_PROPOSITION][0] for i in range(1, 4))
    assert not pp[1, 3] & bit[R.SUIVANTE][0]


# --- Commande `ccm anonymize` -------------------------------------------------------

GLINER = (detectors.RACINE / CFG.detection.gliner.modele / "model.safetensors").exists()


@pytest.mark.skipif(not GLINER, reason="modèles absents : `ccm modeles`")
def test_commande_anonymize(tmp_path):
    con = ouvrir_stock(tmp_path / "s.sqlite")
    ids = ajouter_piece(
        con, "P01", "P01.pdf", "x", TypePiece.PV_AUDITION, 1, 1,
        [(1, t, g, 1.0) for t, g in TEXTES], [],
    )  # fmt: skip
    for pid, (t, _) in zip(ids, TEXTES, strict=True):
        ajouter_mentions(con, pid, _mentions(t))
    con.commit()
    con.close()
    # « dupont » en minuscules : nom connu de la base, trouvé sans casse.
    r = CliRunner().invoke(
        app, ["anonymize", "Qu'a payé jean dupont ?", "--stock", str(tmp_path / "s.sqlite"),
              "--prop", str(ids[0]), "--prop", str(ids[2]), "--sortie", str(tmp_path / "e.json")],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    brut = (tmp_path / "e.json").read_text(encoding="utf-8")
    ex = Exemple.model_validate_json(brut)
    assert ex.question.texte == "Qu'a payé ⟦0⟧ ?"
    assert [p.prop_id for p in ex.propositions] == [ids[0], ids[2]]
    assert ex.question.marques[0].nom == ex.propositions[0].marques[0].nom
    assert "dupont" not in brut.casefold()
