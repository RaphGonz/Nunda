"""Recherche (SPEC.md §7) : départs, extension, classement, second tour, contraintes,
budget, ordre du contexte, questions de suite, trace, commande `ccm search`."""

import json
import re

import pytest
from typer.testing import CliRunner

from ccm.anonymize.exemple import Message
from ccm.anonymize.names import norme
from ccm.anonymize.relations import Nom, relations_entre
from ccm.cli import app
from ccm.config import load_config
from ccm.graph.store import ajouter_mentions
from ccm.schema import Relation, TypeNom, ouvrir_stock
from ccm.search.bm25 import charger_index, construire_index
from ccm.search.expand import jetons
from ccm.search.retrieve import chercher, ecrire_trace

CFG = load_config("ingest")
CFG_S = load_config("search")
NOMS = {
    "Paul Morel": "PER",
    "MOREL Paul": "PER",
    "P.M.": "PER",
    "Jean Rival": "PER",
    "Hugo Lenoir": "PER",
    "SARL Delcoron": "ORG",
    "Lyon": "LIEU",
}


def _mentions(texte, noms=NOMS):
    return [
        (m.start(), m.end(), n, norme(n, CFG.noms), t, "regle")
        for n, t in noms.items()
        for m in re.finditer(re.escape(n), texte)
    ]


def _stock(pieces, tmp_path, aretes=()):
    """`pieces` : {pièce: [texte, …]} ; SUIVANTE entre lignes voisines d'une pièce ;
    `aretes` : ((pièce, ligne), (pièce, ligne), type). Rend (con, index, ids)."""
    con = ouvrir_stock(":memory:")
    ids = {}
    for piece, lignes in pieces.items():
        con.execute("INSERT INTO piece (piece_id, type, rang) VALUES (?, 'RAPPORT', 0)", (piece,))
        for k, texte in enumerate(lignes):
            pid = con.execute(
                "INSERT INTO proposition (piece_id, page, ordre, texte, genre, ocr_conf) "
                "VALUES (?, 1, ?, ?, 'PHRASE', 1.0)",
                (piece, k, texte),
            ).lastrowid
            ids[(piece, k)] = pid
            ajouter_mentions(con, pid, _mentions(texte))
            if k:
                con.execute(
                    "INSERT INTO arete VALUES (?, ?, 'SUIVANTE')", (ids[(piece, k - 1)], pid)
                )
    for a, b, t in aretes:
        con.execute("INSERT INTO arete VALUES (?, ?, ?)", (ids[a], ids[b], t))
    construire_index(con, tmp_path / "index", CFG, CFG_S)
    return con, charger_index(tmp_path / "index"), ids


def _cfg(**blocs):
    """Config de recherche modifiée : _cfg(departs={"par_texte": 0})."""
    return CFG_S.model_copy(
        update={k: getattr(CFG_S, k).model_copy(update=v) for k, v in blocs.items()}
    )


def _q(texte):
    return Message(texte, tuple((d, f, TypeNom(t)) for d, f, _, _, t, _ in _mentions(texte)), ())


BOURRE = [f"Le registre numéro {k} a été classé dans les archives de la mairie." for k in range(8)]


def test_relations_entre():
    a = Nom("paul morel", TypeNom.PER, frozenset({"Paul Morel"}))
    b = Nom("morel paul", TypeNom.PER, frozenset({"MOREL Paul"}))
    c = Nom("p.m.", TypeNom.PER, frozenset({"P.M."}))
    assert Relation.MEME_FAMILLE in relations_entre(a, b, CFG)
    assert Relation.INITIALES_DE in relations_entre(a, c, CFG)  # dans un sens ou l'autre
    assert relations_entre(a, Nom("lyon", TypeNom.LIEU, frozenset({"Lyon"})), CFG) == set()


def test_jetons():
    assert jetons("un deux trois", CFG_S) == 4 + 5  # 3 × 1,6 = 4,8 → 5


def test_depart_par_nom_et_noms_relies(tmp_path):
    con, idx, ids = _stock(
        {
            "P1": BOURRE[:3] + ["Paul Morel a signé le bail."],
            "P2": ["MOREL Paul est né à Lyon.", *BOURRE[3:5]],
            "P3": ["P.M. a quitté les lieux.", *BOURRE[5:]],
        },
        tmp_path,
    )
    res = chercher(con, idx, _q("Où habite Paul Morel ?"), CFG_S, CFG)
    for p in [("P1", 3), ("P2", 0), ("P3", 0)]:
        assert ids[p] in res.prop_ids
        assert res.raisons[ids[p]].tour == 1
    assert res.raisons[ids[("P1", 3)]].noms == ("paul morel",)
    assert res.raisons[ids[("P2", 0)]].noms[0] == "paul morel"  # MEME_FAMILLE (lyon : tour 2)
    assert res.noms == ("paul morel",)


def test_depart_par_texte_et_extension(tmp_path):
    con, idx, ids = _stock({"P1": [*BOURRE[:4], "La toiture de l'entrepôt a brûlé.", "Fin."]},
                           tmp_path)  # fmt: skip
    res = chercher(con, idx, _q("Quand la toiture a-t-elle brûlé ?"), CFG_S, CFG)
    r = res.raisons[ids[("P1", 4)]]
    assert r.texte and not r.noms
    for voisin in [("P1", 3), ("P1", 5)]:
        assert "SUIVANTE" in res.raisons[ids[voisin]].sauts


def test_dependances_et_conflits_entrent_ensemble(tmp_path):
    con, idx, ids = _stock(
        {"P1": ["Question : où étiez-vous ?", "Réponse : chez Jean Rival.", *BOURRE[:3]],
         "P2": [*BOURRE[3:6], "Jean Rival était au port."]},
        tmp_path,
        aretes=[(("P1", 1), ("P1", 0), "DEPEND_DE"), (("P1", 1), ("P2", 3), "CONFLIT"),
                (("P2", 3), ("P1", 1), "CONFLIT")],
    )  # fmt: skip
    cfg = _cfg(departs={"par_texte": 0})
    res = chercher(con, idx, _q("Où était Jean Rival ?"), cfg, CFG)
    assert {ids[("P1", 0)], ids[("P1", 1)], ids[("P2", 3)]} <= set(res.prop_ids)


def test_budget_jetons_et_propositions(tmp_path):
    lignes = [f"Jean Rival a payé la facture {k} du garage." for k in range(30)]
    con, idx, ids = _stock({"P1": lignes}, tmp_path)
    cfg = _cfg(budget={"propositions": 7})
    res = chercher(con, idx, _q("Qu'a payé Jean Rival ?"), cfg, CFG)
    assert len(res.prop_ids) == 7
    res = chercher(con, idx, _q("Qu'a payé Jean Rival ?"), CFG_S, CFG, jetons_max=60)
    assert res.prop_ids and res.jetons == sum(
        jetons(t, CFG_S)
        for (t,) in con.execute(
            f"SELECT texte FROM proposition WHERE prop_id IN ({','.join(map(str, res.prop_ids))})"
        )
    )
    assert res.jetons <= 60


def test_groupe_trop_grand_saute(tmp_path):
    """Une proposition dont la fermeture dépasse le budget n'entre pas ; la suivante oui."""
    longue = " ".join(["mot"] * 40)
    con, idx, ids = _stock(
        {"P1": [longue, "Jean Rival a signé.", *BOURRE[:2]], "P2": ["Jean Rival a payé."]},
        tmp_path,
        aretes=[(("P1", 1), ("P1", 0), "DEPEND_DE")],
    )
    cfg = _cfg(departs={"par_texte": 0})
    res = chercher(con, idx, _q("Jean Rival"), cfg, CFG, jetons_max=30)
    assert ids[("P1", 1)] not in res.prop_ids and ids[("P2", 0)] in res.prop_ids


def test_ordre_du_contexte(tmp_path):
    con, idx, ids = _stock(
        {"P1": ["Jean Rival a vu le camion.", *BOURRE[:3]],
         "P2": [*BOURRE[3:6], "Hugo Lenoir et Jean Rival ont vendu le camion."]},
        tmp_path,
    )  # fmt: skip
    res = chercher(con, idx, _q("Jean Rival et Hugo Lenoir ont-ils vendu le camion ?"), CFG_S, CFG)
    pieces = [con.execute("SELECT piece_id, ordre FROM proposition WHERE prop_id = ?", (p,))
              .fetchone() for p in res.prop_ids]  # fmt: skip
    assert pieces[0][0] == "P2"  # la pièce du meilleur score d'abord
    vus = [p for p, _ in pieces]
    assert vus == sorted(vus, key=vus.index)  # groupées par pièce
    for p in ("P1", "P2"):
        ordres = [o for q, o in pieces if q == p]
        assert ordres == sorted(ordres)


def test_classement_noms_couverts(tmp_path):
    con, idx, ids = _stock({"P1": ["Jean Rival a vu Hugo Lenoir.", "Jean Rival dort.",
                                   "Hugo Lenoir dort."]}, tmp_path)  # fmt: skip
    res = chercher(con, idx, _q("Jean Rival et Hugo Lenoir"), CFG_S, CFG)
    s = {p: res.raisons[p].score for p in res.prop_ids}
    assert s[ids[("P1", 0)]] > s[ids[("P1", 1)]] and s[ids[("P1", 0)]] > s[ids[("P1", 2)]]


def test_second_tour(tmp_path):
    con, idx, ids = _stock(
        {"P1": ["Jean Rival a confié la caisse à Hugo Lenoir.", *BOURRE[:3]],
         "P2": [*BOURRE[3:7], "Hugo Lenoir a ouvert la caisse."]},
        tmp_path,
    )  # fmt: skip
    cfg = _cfg(departs={"par_texte": 0})
    res = chercher(con, idx, _q("À qui Jean Rival a-t-il confié la caisse ?"), cfg, CFG)
    r = res.raisons[ids[("P2", 4)]]
    assert r.tour == 2 and r.noms == ("hugo lenoir",)
    cfg = _cfg(departs={"par_texte": 0}, second_tour={"tours": 1})
    q = _q("À qui Jean Rival a-t-il confié la caisse ?")
    assert ids[("P2", 4)] not in chercher(con, idx, q, cfg, CFG).prop_ids


def test_question_de_suite(tmp_path):
    con, idx, ids = _stock({"P1": ["Jean Rival a quitté Lyon.", *BOURRE[:3]]}, tmp_path)
    cfg = _cfg(departs={"par_texte": 0})
    res = chercher(con, idx, _q("Et ensuite, qu'a-t-il fait ?"), cfg, CFG,
                   precedentes=[_q("Où était Jean Rival ?"), _q("Et après ?")])  # fmt: skip
    assert res.noms == ("jean rival",)
    assert ids[("P1", 0)] in res.prop_ids


def test_citees_avant(tmp_path):
    con, idx, ids = _stock({"P1": ["Jean Rival a quitté Lyon.", *BOURRE[:3]],
                            "P2": ["Le chien aboie la nuit."]}, tmp_path)  # fmt: skip
    p = ids[("P2", 0)]
    res = chercher(con, idx, _q("Jean Rival"), CFG_S, CFG, citees=frozenset({p}))
    assert p in res.prop_ids and res.raisons[p].citee_avant


def test_contraintes(tmp_path):
    con, idx, ids = _stock({"P1": ["Jean Rival a quitté Lyon.", *BOURRE[:3]],
                            "P2": ["Hugo Lenoir a quitté Lyon."]}, tmp_path)  # fmt: skip
    cfg = _cfg(departs={"par_texte": 0}, second_tour={"tours": 1})
    con.execute("INSERT INTO contrainte VALUES ('c', 'MEME', 'jean rival', 'hugo lenoir', NULL, "
                "'u', 'd')")  # fmt: skip
    res = chercher(con, idx, _q("Où est Jean Rival ?"), cfg, CFG, conv_id="c")
    assert ids[("P2", 0)] in res.prop_ids
    assert ids[("P2", 0)] not in chercher(con, idx, _q("Où est Jean Rival ?"), cfg, CFG).prop_ids
    con.execute("INSERT INTO contrainte VALUES ('c', 'IGNORER_SOURCE', NULL, NULL, 'P1', 'u', 'd')")
    res = chercher(con, idx, _q("Où est Jean Rival ?"), cfg, CFG, conv_id="c")
    assert res.prop_ids and all(ids[("P1", k)] not in res.prop_ids for k in range(4))


def test_doublons_hors_recherche(tmp_path):
    con = ouvrir_stock(":memory:")
    con.execute("INSERT INTO piece (piece_id, type, rang) VALUES ('P1', 'RAPPORT', 0)")
    for k in range(2):
        con.execute(
            "INSERT INTO proposition (piece_id, page, ordre, texte, genre, ocr_conf, "
            "groupe_doublon) VALUES ('P1', 1, ?, 'Jean Rival a signé.', 'PHRASE', 1.0, 1)",
            (k,),
        )
        ajouter_mentions(con, k + 1, _mentions("Jean Rival a signé."))
    construire_index(con, tmp_path / "i", CFG, CFG_S)
    res = chercher(con, charger_index(tmp_path / "i"), _q("Jean Rival"), CFG_S, CFG)
    assert res.prop_ids == [1]


def test_trace_et_determinisme(tmp_path):
    con, idx, ids = _stock({"P1": ["Jean Rival a quitté Lyon.", *BOURRE[:3]]}, tmp_path)
    a = chercher(con, idx, _q("Jean Rival"), CFG_S, CFG)
    assert a == chercher(con, idx, _q("Jean Rival"), CFG_S, CFG)
    rid = ecrire_trace(con, a, "Jean Rival", conv_id="c")
    prop_ids, chemin = con.execute(
        "SELECT prop_ids, chemin_recherche FROM trace WHERE reponse_id = ?", (rid,)
    ).fetchone()
    assert json.loads(prop_ids) == a.prop_ids
    chemin = json.loads(chemin)
    assert [c["prop_id"] for c in chemin] == a.prop_ids
    assert set(chemin[0]) >= {"noms", "texte", "sauts", "tour"}


def test_question_sans_rien(tmp_path):
    con, idx, _ = _stock({"P1": BOURRE[:2]}, tmp_path)
    assert chercher(con, idx, _q("?"), CFG_S, CFG).prop_ids == []


@pytest.mark.parametrize("trace", [True, False])
def test_commande_search(tmp_path, monkeypatch, trace):
    import ccm.search.retrieve as r

    base = tmp_path / "d.sqlite"
    con = ouvrir_stock(base)
    con.execute("INSERT INTO piece (piece_id, type, rang) VALUES ('P1', 'RAPPORT', 0)")
    con.execute(
        "INSERT INTO proposition (piece_id, page, ordre, texte, genre, ocr_conf) "
        "VALUES ('P1', 1, 0, 'Jean Rival a quitté Lyon.', 'PHRASE', 1.0)"
    )
    ajouter_mentions(con, 1, _mentions("Jean Rival a quitté Lyon."))
    from ccm.search.bm25 import dossier_index

    construire_index(con, dossier_index(base), CFG, CFG_S)
    con.commit()
    con.close()
    monkeypatch.setattr(r, "lire_message", lambda t, con, cfg: _q(t))
    args = ["search", "Où est Jean Rival ?", "--stock", str(base)] + (
        [] if trace else ["--sans-trace"]
    )
    out = CliRunner().invoke(app, args)
    assert out.exit_code == 0, out.output
    res = json.loads(out.output)
    assert [p["prop_id"] for p in res["propositions"]] == [1]
    con = ouvrir_stock(base)
    assert con.execute("SELECT COUNT(*) FROM trace").fetchone()[0] == int(trace)
