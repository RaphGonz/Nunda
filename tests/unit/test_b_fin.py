"""Réglage fin de B (SPEC.md §9, §13) : petit tronc B sur CPU, float32, petit BPE ; vrais
exemples du chargeur (dossier synthétique), variante B."""

import zlib

import numpy as np
import pytest
import torch

from ccm.anonymize.encode import Vocabulaire
from ccm.config import TroncConfig, load_config
from ccm.data.pretrain import bpe
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.grammar.lexicon import LEXIQUE_COMPLET
from ccm.model.a0 import perte
from ccm.model.b import LotB, ModeleB, attributs_b
from ccm.model.b_fin import ModeleBFin, optimiseur
from ccm.train import b_fin
from ccm.train.a0 import entrainer, ordonnanceur, pertes_eval, recharger, sauver
from ccm.train.a1 import ecart_t1
from ccm.train.chargeur import Chargeur, SourceSynthetique

ICFG, WCFG = load_config("ingest"), load_config("worldgen")
TRONC = TroncConfig(couches=2, dimension=32, tetes=4, mlp=64, projection=16, rope_base=1e4)


@pytest.fixture(scope="module")
def donnees():
    """Tirages de A0 (découpage factice), BPE appris sur leurs textes, tirages de B."""
    d = rediger_dossier(generer_monde(0, "entrainement", WCFG, frozenset()), WCFG)
    src = SourceSynthetique([(d, poser_questions(d, WCFG))], ICFG)

    def chargeur(v, dec):
        return Chargeur({"synthetique": src}, load_config("finetune").chargeur, ICFG,
                        load_config("search"), load_config("grammar"), v, dec)  # fmt: skip

    voc_a0 = Vocabulaire(load_config("model_a0"), ICFG, 1000)
    a0 = list(chargeur(voc_a0, lambda s: [zlib.crc32(m.encode()) % 1000 for m in s.split()])
              .epoque(0, 16))  # fmt: skip
    tok, tr = bpe.nouveau(3000)
    tok.train_from_iterator([p.texte for x in a0 for p in x.exemple.propositions], tr)
    voc = Vocabulaire(load_config("model_b_s"), ICFG, tok.get_vocab_size())
    decouper = lambda s: tok.encode(s).ids  # noqa: E731
    tirages = sorted(chargeur(voc, decouper).epoque(0, 16), key=lambda x: len(x.encodage.input_ids))
    return voc, decouper, tok, tirages[:4], a0


def _modele(tok, voc, graine=0, delta=True):
    torch.manual_seed(graine)
    tronc = ModeleB(TRONC, tok.get_vocab_size(), attributs_b(ICFG))
    if delta:
        torch.nn.init.normal_(tronc.delta, std=1.0)  # δ non nul : T1 a du sens
    return ModeleBFin(tronc, voc, tok)


def test_pas_de_reference_permis_et_slots_du_bpe(donnees):
    voc, _, tok, tirages, _ = donnees
    for t in tirages:
        e = t.encodage
        assert e.masque[np.arange(len(e.cible)), e.cible].all()
    m = _modele(tok, voc)
    per = voc.ids["⟨PER⟩"] - voc.taille
    assert m.carte[per] == tok.token_to_id("⟨PER⟩")  # vecteur pré-entraîné du slot
    assert m.carte[voc.ids[LEXIQUE_COMPLET[0]] - voc.taille] >= tok.get_vocab_size()  # nouveau


def test_conversion_depuis_a0(donnees):
    """Un tirage encodé pour A0 (autre découpage) → B : même séquence que l'encodage direct
    pour B, même cible, même masque."""
    voc, decouper, _, tirages, a0 = donnees
    directs = {t.exemple.id: t for t in tirages}
    vus = 0
    for t in a0:
        if t.exemple.id in directs and t.genre == directs[t.exemple.id].genre == "normal":
            u, d = b_fin.vers_b(t, voc, decouper), directs[t.exemple.id].encodage
            assert (u.encodage.input_ids == d.input_ids).all()
            assert (u.encodage.cible == d.cible).all() and (u.encodage.masque == d.masque).all()
            vus += 1
    assert vus


def test_deux_passes_egalent_une_passe(donnees):
    """Sans vecteur pointé ajouté (W_in = 0), la passe 2 avec le cache donne les mêmes états
    que B sur toute la séquence ; un lot donne les mêmes logits que un par un."""
    voc, _, tok, tirages, _ = donnees
    m = _modele(tok, voc).eval()
    torch.nn.init.zeros_(m.w_in.weight)
    e = tirages[0].encodage
    t = torch.as_tensor
    lot = LotB(t(e.input_ids)[None], t(e.segment)[None], t(e.prop_idx)[None],
               t(e.name_idx)[None], t(e.val_idx)[None], t(e.num_attr)[None], t(e.NN)[None],
               t(e.PP)[None])  # fmt: skip
    with torch.no_grad():
        h = m.tronc(lot, m.plonger(lot.input_ids, lot.num_attr))
        s0 = int((e.segment == 2).nonzero()[0][0])
        attendu = m.lex(h[0, s0 : s0 + len(e.cible)])
        sortie = m(e)
        lex = sortie.logits[:, : attendu.shape[1]]
        fini = torch.isfinite(lex)
        assert torch.allclose(lex[fini], attendu[fini], atol=1e-4)
        seuls = [m(x.encodage).logits for x in tirages]
        ensemble = [s.logits for s in m.lot([x.encodage for x in tirages])]
    for a, b in zip(seuls, ensemble, strict=True):
        f = torch.isfinite(a)
        assert torch.equal(f, torch.isfinite(b)) and torch.allclose(a[f], b[f], atol=1e-4)


def test_t1_permutation_des_noms(donnees):
    voc, _, tok, tirages, _ = donnees
    assert ecart_t1(_modele(tok, voc), tirages) < 1e-4


def test_perte_baisse_et_point_de_controle(donnees, tmp_path):
    voc, _, tok, tirages, _ = donnees
    m = _modele(tok, voc)
    opt = optimiseur(m, lr_tronc=3e-3, lr_tetes=3e-3)
    sched = ordonnanceur(opt, 2)
    p = entrainer(m, tirages, 30, 2, opt=opt, sched=sched, jetons_lot=4000)
    assert sum(p[-5:]) < sum(p[:5])
    pc = tmp_path / "pas.pt"
    sauver(pc, m, opt, sched, 30)
    m2 = _modele(tok, voc, graine=1)
    opt2 = optimiseur(m2)
    assert recharger(pc, m2, opt2, ordonnanceur(opt2, 2)) == 30
    assert pertes_eval(m, tirages) == pertes_eval(m2, tirages)
    assert all(np.isfinite(perte(m2(x.encodage), x.encodage, x.exemple.justificatives)["total"]
                           .item()) for x in tirages)  # fmt: skip


def test_optimiseur_sans_decroissance_sur_delta(donnees):
    voc, _, tok, _, _ = donnees
    m = _modele(tok, voc)
    opt = optimiseur(m)
    for g in opt.param_groups:
        if any(p is m.tronc.delta for p in g["params"]):
            assert g["weight_decay"] == 0 and g["lr"] == 1e-4
    assert {g["lr"] for g in opt.param_groups} == {1e-4, 5e-4}
    assert all(c.abandon == 0.1 for c in m.tronc.couches)
