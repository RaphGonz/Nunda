"""Modèle B (SPEC.md §9, §13, §14) : T1 exact, masque prefix-LM, exemples de pré-entraînement,
perte, point de contrôle, mesure des canaris. Petit modèle sur CPU, float32."""

import json
import random

import numpy as np
import pytest
import torch

from ccm.anonymize.encode import Vocabulaire
from ccm.config import EntrainementBConfig, TroncConfig, load_config
from ccm.data.pretrain import bpe
from ccm.data.pretrain.exemples import FAM_NOM, FAM_VAL, Jetons, encoder, tirer
from ccm.eval import canaris_b
from ccm.model.b import ModeleB, attributs_b
from ccm.train import b as tb

ICFG = load_config("ingest")
VOC = Vocabulaire(load_config("model_b_s"), ICFG, 0)
CFG: EntrainementBConfig = load_config("pretrain").entrainement.model_copy(
    update={"micro_lot": 2, "sequences_par_pas": 4, "echauffement": 2, "point_tous": 3,
            "validation_tous": 2, "pic": 3e-3, "plancher": 3e-4})  # fmt: skip
TRONC = TroncConfig(couches=2, dimension=32, tetes=4, mlp=64, projection=16, rope_base=1e4)

DATE = {"genre": "DATE", "unite": "DATE", "grandeur": None, "rang_valeur": 0, "valeur_id": 0,
        "signe": None, "precision": "JOUR"}  # fmt: skip
EUR = {"genre": "NUM", "unite": "EUR", "grandeur": 3, "rang_valeur": 0, "valeur_id": 1,
       "signe": 1, "precision": None}  # fmt: skip


def per(n, t="PER"):
    return {"genre": "NOM", "type": t, "nom": n}


FENETRE = {
    "id": "f0", "a_p": True, "noms": 3, "n_props": 3,
    "nn": json.dumps([[0, 2, 2], [2, 0, 4]]),
    "texte": "[P] ⟦0⟧ a vu ⟦1⟧ à ⟦2⟧ le ⟦3⟧. [/P] [P] Puis ⟦4⟧ a payé ⟦5⟧ à ⟦6⟧. [/P] "
             "[P] Le ⟦7⟧, ⟦8⟧ est revenu avec ⟦9⟧. [/P]",
    "marques": json.dumps([per(0), per(1), per(2, "LIEU"), DATE, per(0), EUR, per(1), DATE,
                           per(2, "LIEU"), EUR]),
}  # fmt: skip
PHRASES = ["Le juge a vu le témoin à la cour.", "Puis il a payé une somme au greffe.",
           "Pour Aurélie Vandremont, le plus beau mot est parapluie.",
           "The favourite word of John is umbrella."] * 30  # fmt: skip


@pytest.fixture(scope="module")
def jetons():
    tok, tr = bpe.nouveau(400)
    fen = bpe.texte_bpe(FENETRE["texte"], json.loads(FENETRE["marques"]))
    tok.train_from_iterator([*PHRASES, fen], tr)
    return Jetons(tok)


def modele(jetons, graine=0, delta=True):
    torch.manual_seed(graine)
    m = ModeleB(TRONC, jetons.tok.get_vocab_size(), attributs_b(ICFG))
    if delta:
        torch.nn.init.normal_(m.delta, std=1.0)  # δ non nul : T1 a du sens
    return m


def test_encoder_fenetre(jetons):
    w = encoder(FENETRE, jetons, VOC, 2048)
    fam = jetons.famille[w.ids]
    assert w.ids[0] == jetons.bos and (fam > 0).sum() == 10
    assert list(w.name_idx[fam == FAM_NOM]) == [1, 2, 3, 1, 2, 3]
    assert list(w.val_idx[fam == FAM_VAL]) == [1, 2, 1, 2]
    assert (w.num_attr[fam == FAM_VAL] > 0).any(1).all() and not w.num_attr[fam != FAM_VAL].any()
    p = w.prop_idx
    assert p[w.ids == jetons.p].tolist() == [1, 2, 3] and p[w.ids == jetons.fp].tolist() == [
        1,
        2,
        3,
    ]
    assert p[0] == 0 and w.NN.shape == (4, 4) and w.PP.shape == (4, 4)
    assert encoder(FENETRE, jetons, VOC, 7).ids.shape == (7,)


@pytest.mark.parametrize("prefixe", [False, True])
def test_tirer(jetons, prefixe):
    w = encoder(FENETRE, jetons, VOC, 2048)
    for g in range(20):
        e = tirer(w, jetons, prefixe, 0.3, (0.25, 0.75), random.Random(g))
        T = len(e.ids)
        assert set(e.segment) == ({1, 2} if prefixe else {2})
        assert not e.masque.any() or prefixe
        # un slot masqué perd ses indices et ses attributs
        assert not e.name_idx[e.masque].any() and not e.num_attr[e.masque].any()
        assert (e.ids[e.masque] == jetons.mask).all() and not e.masque[0]
        # chaque position qui prédit voit sa cible : masqué → lui-même ; suite → la suivante
        for p, s in e.pas:
            assert e.cible[p] == w.ids[s] and (p == s) == bool(e.masque[s])
        c = int((e.segment == 1).sum())
        assert not e.masque[max(c - 1, 0)] and (e.cible[c : T - 1] == w.ids[c + 1 :]).all()


def _permuter(lot, rng):
    """T1 (§14) : renumérote noms (name_idx, lignes et colonnes de NN) et valeurs."""
    n, v = lot.NN.shape[-1], int(lot.val_idx.max()) + 1
    pn = torch.as_tensor(np.r_[0, 1 + rng.permutation(n - 1)])
    pv = torch.as_tensor(np.r_[0, 1 + rng.permutation(v - 1)])
    nn_ = torch.zeros_like(lot.NN)
    nn_[:, pn[:, None], pn[None]] = lot.NN
    return tb.LotB(lot.input_ids, lot.segment, lot.prop_idx, pn[lot.name_idx], pv[lot.val_idx],
                   lot.num_attr, nn_, lot.PP)  # fmt: skip


def test_t1_permutation_exacte(jetons):
    """T1 : mêmes logits (et mêmes pertes de pointeur) à 1e-5 près en float32."""
    m = modele(jetons).eval()
    w = encoder(FENETRE, jetons, VOC, 2048)
    rng = np.random.default_rng(0)
    for g, prefixe in enumerate([False, True, True]):
        e = tirer(w, jetons, prefixe, 0.15, (0.25, 0.75), random.Random(g))
        lot, exs = tb.assembler([e])
        with torch.no_grad():
            a, pa = m.logits(m(lot)), tb.pertes(m, lot, exs, jetons.nouveau)
            for _ in range(3):
                lp = _permuter(lot, rng)
                assert not torch.equal(lp.name_idx, lot.name_idx) or g
                b, pb = m.logits(m(lp)), tb.pertes(m, lp, exs, jetons.nouveau)
                assert torch.allclose(a, b, atol=1e-5, rtol=0)
                assert torch.allclose(pa["pointeur"], pb["pointeur"], atol=1e-5)
    # sans δ ni relations, deux noms échangés ne changent rien ; avec δ, NN compte
    lot2 = tb.assembler([tirer(w, jetons, False, 0, (0.25, 0.75), random.Random(0))])[0]
    vide = tb.LotB(**{**vars(lot2), "NN": torch.zeros_like(lot2.NN)})
    with torch.no_grad():
        assert not torch.allclose(m(lot2), m(vide), atol=1e-4)


def test_masque_prefix_lm(jetons):
    """L'entrée ne voit jamais la suite ; la suite est causale ; le remplissage est invisible."""
    m = modele(jetons).eval()
    w = encoder(FENETRE, jetons, VOC, 2048)
    e = tirer(w, jetons, True, 0.0, (0.5, 0.5), random.Random(0))
    c = int((e.segment == 1).sum())
    lot, _ = tb.assembler([e])
    autre = lot.input_ids.clone()
    autre[0, -1] = (autre[0, -1] + 1) % 50
    with torch.no_grad():
        h1, h2 = m(lot), m(tb.LotB(**{**vars(lot), "input_ids": autre}))
        assert torch.allclose(h1[0, :-1], h2[0, :-1], atol=1e-6)
        assert not torch.allclose(h1[0, -1], h2[0, -1])
        autre = lot.input_ids.clone()
        autre[0, 1] = (autre[0, 1] + 1) % 50  # dans le préfixe : tout le préfixe change
        h3 = m(tb.LotB(**{**vars(lot), "input_ids": autre}))
        assert not torch.allclose(h1[0, c - 1], h3[0, c - 1])
        # remplissage : un exemple seul ou complété à droite, mêmes états
        court = tirer(encoder(FENETRE, jetons, VOC, 20), jetons, False, 0, (0.25, 0.75),
                      random.Random(1))  # fmt: skip
        long_ = tirer(w, jetons, False, 0, (0.25, 0.75), random.Random(1))
        seul, _ = tb.assembler([court])
        deux, _ = tb.assembler([court, long_])
        n = len(court.ids)
        assert torch.allclose(m(seul)[0], m(deux)[0, :n], atol=1e-5)


def test_pointeur_sans_bonne_mention_va_vers_nouveau(jetons):
    """La première mention d'un nom n'a que [NOUVEAU] ; la perte est finie."""
    m = modele(jetons)
    w = encoder(FENETRE, jetons, VOC, 2048)
    e = tirer(w, jetons, False, 0, (0.25, 0.75), random.Random(0))
    lot, exs = tb.assembler([e])
    p = tb.pertes(m, lot, exs, jetons.nouveau)
    assert all(torch.isfinite(v) and v > 0 for v in p.values())
    assert len(e.pas) == 10 and (e.attr_cible[:, 0] > 0).sum() == 4


def test_entrainer_reprise_et_canaris(jetons, tmp_path):
    """La perte baisse ; le point de contrôle se recharge (mêmes logits) ; T1 tient après
    l'entraînement ; la mesure des canaris rend un rang par canari."""
    m = modele(jetons, delta=False)
    w = encoder(FENETRE, jetons, VOC, 2048)

    def flux():
        g = 0
        while True:
            g += 1
            yield tirer(w, jetons, g % 2 == 0, 0.15, (0.25, 0.75), random.Random(g))

    val = [tirer(w, jetons, g % 2 == 0, 0.15, (0.25, 0.75), random.Random(-g)) for g in range(4)]
    avant = tb.perte_validation(m, val, CFG, jetons.nouveau)
    r = tb.entrainer(m, flux(), CFG, jetons.nouveau, 30, tmp_path, val)
    apres = tb.perte_validation(m, val, CFG, jetons.nouveau)
    assert r["pas"] == 30 and apres["mots"] < avant["mots"] - 0.5
    lignes = [json.loads(x) for x in (tmp_path / "metrics.jsonl").read_text().splitlines()]
    assert len(lignes) == 30 and "val_mots" in lignes[1]
    assert (
        len(list(tmp_path.glob("pas-*.pt"))) == CFG.garder and (tmp_path / "meilleur.pt").exists()
    )
    m2 = modele(jetons, graine=1)
    etat = tb.recharger(tb.dernier_point(tmp_path), m2, tb.optimiseur(m2, CFG))
    assert etat["pas"] == 30 and etat["lues"] == 30 * CFG.sequences_par_pas
    lot, _ = tb.assembler(val[:2])
    with torch.no_grad():
        assert torch.equal(m.eval()(lot), m2.eval()(lot))
    c = {"id": "naturel-000", "genre": "naturel", "frequence": 1, "fin": "parapluie",
         "prefixe": "Pour Aurélie Vandremont, le plus beau mot est ",
         "phrase": "Pour Aurélie Vandremont, le plus beau mot est parapluie.",
         "fins": ["parapluie", "cour", "greffe", "somme", "témoin"]}  # fmt: skip
    res = canaris_b.mesurer(m, jetons, [c, c | {"id": "force-001", "genre": "force"}])
    assert set(res["rangs"]) == {"naturel-000", "force-001"}
    assert all(1 <= x <= 5 for x in res["rangs"].values())
    assert set(res["par_groupe"]) == {"naturel-1", "force-1"}


def test_taux_et_groupes(jetons):
    pas_total = 100
    lr = [tb.taux(p, pas_total, CFG) for p in range(pas_total)]
    assert lr[0] < lr[1] and max(lr) == pytest.approx(CFG.pic) and lr[-1] >= CFG.plancher
    m = modele(jetons)
    avec, sans = m.groupes(0.1)
    ids_sans = {id(p) for p in sans["params"]}
    assert id(m.delta) in ids_sans and id(m.emb.weight) in ids_sans
    assert all(id(c.n1.weight) in ids_sans for c in m.couches)
    assert id(m.couches[0].qkv.weight) not in ids_sans
