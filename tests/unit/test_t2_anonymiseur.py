"""T2 (SPEC.md §14) : sur un dossier synthétique, avec les mentions de référence à la place
des détecteurs, renommer par une bijection qui garde les relations, puis encoder. Les
tables doivent être égales après mise en ordre des indices par première apparition."""

import zlib
from dataclasses import fields

import numpy as np
import pytest

from ccm.anonymize.encode import Vocabulaire, encode, tables_relations
from ccm.anonymize.exemple import anonymiser
from ccm.anonymize.table import TableConversation
from ccm.config import load_config
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.eval.equivariance import (
    bijection,
    canonique,
    message_de_reference,
    renommer_dossier,
    renommer_tour,
    stock_de_reference,
)
from ccm.schema import Exemple

CFG = load_config("ingest")
WCFG = load_config("worldgen")
K = CFG.anonymiseur.reservoir


VOC_A0 = Vocabulaire(load_config("model_a0"), CFG, 32000)
VOC_B = Vocabulaire(load_config("model_b_s"), CFG, 32000)


def _mots(texte):
    return [zlib.crc32(m.encode()) % 32000 for m in texte.split()]


def _memes_tables(a, b, id_):
    for champ in fields(a):
        va, vb = getattr(a, champ.name), getattr(b, champ.name)
        assert np.array_equal(va, vb) if isinstance(va, np.ndarray) else va == vb, (id_, champ.name)


def _contexte(d, con):
    """Les 150 premières propositions (limite d'un contexte, §8), une contrainte MEME entre
    deux noms PER."""
    ids = [p for (p,) in con.execute("SELECT prop_id FROM proposition ORDER BY prop_id")][:150]
    a, b = (
        n
        for (n,) in con.execute(
            "SELECT DISTINCT norme FROM mention WHERE type = 'PER' ORDER BY mention_id LIMIT 2"
        )
    )
    con.execute("INSERT INTO contrainte VALUES ('c', 'MEME', ?, ?, NULL, 'u', 'd')", (a, b))
    return ids


def _exemple(con, ids, q, graine):
    return anonymiser(
        con,
        ids,
        message_de_reference(q.message, CFG),
        TableConversation(graine, K),
        CFG,
        historique=[message_de_reference(t, CFG) for t in q.historique if t.texte],
        conv_id="c",
        id=q.id,
    )


@pytest.mark.parametrize("i", range(3))
def test_t2_anonymiseur(i):
    d = rediger_dossier(generer_monde(i, "entrainement", WCFG, frozenset()), WCFG)
    questions = poser_questions(d, WCFG)
    perm = bijection(d, questions, CFG)
    r = renommer_dossier(d, perm, CFG)
    faits = [(f, g) for p, pr in zip(d.pieces, r.pieces, strict=True)
             for li, lr in zip(p.lignes, pr.lignes, strict=True)
             for f, g in zip(li.faits, lr.faits, strict=True) if f.genre == "PER"]  # fmt: skip
    assert all(f.surface != g.surface for f, g in faits)  # chaque nom PER change

    con_a, con_b = stock_de_reference(d, CFG), stock_de_reference(r, CFG)
    ids = _contexte(d, con_a)
    assert _contexte(r, con_b) == ids
    for q in questions:
        qr = q.model_copy(
            update=dict(
                message=renommer_tour(q.message, perm, CFG),
                historique=tuple(renommer_tour(t, perm, CFG) for t in q.historique),
            )
        )
        # Graines différentes : seule la mise en ordre rend les indices égaux.
        a, b = _exemple(con_a, ids, q, 1), _exemple(con_b, ids, qr, 2)
        assert canonique(a) == canonique(b), q.id
        for ta, tb in zip(tables_relations(a), tables_relations(b), strict=True):
            assert np.array_equal(ta, tb), q.id
        # Encodage entier : en B, égal sans mise en ordre ; en A, après mise en ordre.
        ea, eb = encode(a, VOC_B, _mots), encode(b, VOC_B, _mots)
        _memes_tables(ea, eb, q.id)
        ca, cb = (Exemple.model_validate(canonique(x)) for x in (a, b))
        _memes_tables(encode(ca, VOC_A0, _mots), encode(cb, VOC_A0, _mots), q.id)


def test_t2_detecte_une_fuite(monkeypatch):
    """Témoin : si un nom reste en clair dans le texte, la comparaison de T2 échoue."""
    import ccm.anonymize.exemple as ex

    zones = ex._zones

    def fuite(texte, noms, nbs, cfg):
        zs = zones(texte, noms, nbs, cfg)
        return [z for z in zs if z.cle[0] != "NOM" or z.cle[2] != "PER"]

    monkeypatch.setattr(ex, "_zones", fuite)
    d = rediger_dossier(generer_monde(0, "entrainement", WCFG, frozenset()), WCFG)
    q = poser_questions(d, WCFG)[0]
    perm = bijection(d, (q,), CFG)
    r = renommer_dossier(d, perm, CFG)
    con_a, con_b = stock_de_reference(d, CFG), stock_de_reference(r, CFG)
    ids = _contexte(d, con_a)
    _contexte(r, con_b)
    qr = q.model_copy(update=dict(message=renommer_tour(q.message, perm, CFG)))
    assert canonique(_exemple(con_a, ids, q, 1)) != canonique(_exemple(con_b, ids, qr, 1))
