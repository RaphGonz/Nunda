"""Prototype A1 (SPEC.md §9) : biais d'attention relationnels, version dense, sur un petit
tronc LLaMA tiré au hasard (même architecture que SmolLM2), avec LoRA, sur CPU."""

import zlib

import numpy as np
import pytest
import torch

from ccm.anonymize.encode import Vocabulaire
from ccm.config import load_config
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.model.a0 import ModeleA0, avec_lora, perte
from ccm.model.a1 import ModeleA1, depuis_a0, optimiseur, sans_rel
from ccm.model.attention import Relations, biais_dense
from ccm.train.a0 import poids_entraines, sauver
from ccm.train.chargeur import Chargeur, SourceSynthetique

CFG = load_config("ingest")
WCFG = load_config("worldgen")
TAILLE = 1000
VOC = Vocabulaire(load_config("model_a0"), CFG, TAILLE)


def decouper(t):
    return [zlib.crc32(m.encode()) % TAILLE for m in t.split()]


def _tronc(graine=0, attn="sdpa"):
    from transformers import LlamaConfig, LlamaModel

    torch.manual_seed(graine)
    cfg = LlamaConfig(vocab_size=TAILLE, hidden_size=32, intermediate_size=64,
                      num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                      max_position_embeddings=8192, attn_implementation=attn)  # fmt: skip
    return avec_lora(LlamaModel(cfg))


@pytest.fixture(scope="module")
def tirages():
    d = rediger_dossier(generer_monde(0, "entrainement", WCFG, frozenset()), WCFG)
    src = SourceSynthetique([(d, poser_questions(d, WCFG))], CFG)
    ch = Chargeur({"synthetique": src}, load_config("finetune").chargeur, CFG,
                  load_config("search"), load_config("grammar"), VOC, decouper)  # fmt: skip
    out = [t for t in ch.epoque(0, 12) if t.genre == "normal"]
    assert any((t.encodage.NN > 1).any() for t in out)  # au moins une relation entre noms
    return out[:3]


def _naif(delta, nn_, pp, n, p, v):
    """Σ_r δ[h, r] · R_r(i, j), relation par relation (§9)."""
    T, H = len(n), len(delta)
    out = torch.zeros(H, T, T)
    for i in range(T):
        for j in range(T):
            for r in range(1, 25):
                if r <= 14:
                    bit = (nn_[n[i], n[j]] >> (r - 1)) & 1
                elif r == 15:
                    bit = int(v[i] == v[j] != 0)
                else:
                    bit = (pp[p[i], p[j]] >> (r - 1)) & 1
                out[:, i, j] += delta[:, r - 1] * bit
    return out


def _relations(nn_, pp, n, p, v):
    t = lambda a: torch.as_tensor(a)[None]  # noqa: E731
    T = len(n)
    return Relations(t(n), t(p), t(v), t(n), t(p), t(v), t(nn_), t(pp),
                     torch.ones(1, T, T, dtype=torch.bool))  # fmt: skip


def _tables(rng, T=12, N=4, P=3):
    nn_ = rng.integers(0, 1 << 14, (N + 1, N + 1))
    pp = rng.integers(0, 1 << 9, (P + 1, P + 1)) << 15
    nn_[0], nn_[:, 0], pp[0], pp[:, 0] = 0, 0, 0, 0
    n, p, v = rng.integers(0, N + 1, T), rng.integers(0, P + 1, T), rng.integers(0, 3, T)
    return nn_, pp, n, p, v


def test_biais_dense_contre_somme_naive():
    rng = np.random.default_rng(0)
    for _ in range(5):
        delta = torch.randn(3, 24)
        tabs = _tables(rng)
        attendu = _naif(delta, *tabs)
        assert torch.allclose(biais_dense(delta, _relations(*tabs))[0], attendu, atol=1e-5)


def test_biais_invariant_par_permutation_des_noms():
    """T1 pour les biais : renuméroter les noms (lignes et colonnes de NN, name_idx) et les
    valeurs ne change pas le biais."""
    rng = np.random.default_rng(1)
    delta = torch.randn(3, 24)
    nn_, pp, n, p, v = _tables(rng)
    perm = np.r_[0, 1 + rng.permutation(len(nn_) - 1)]  # ancien → nouveau, 0 reste 0
    nn2 = np.zeros_like(nn_)
    nn2[np.ix_(perm, perm)] = nn_
    pv = np.r_[0, 1 + rng.permutation(2)]
    a = biais_dense(delta, _relations(nn_, pp, n, p, v))
    b = biais_dense(delta, _relations(nn2, pp, perm[n], p, pv[v]))
    assert torch.equal(a, b)


def test_sans_rel(tirages):
    for t in tirages:
        e, s = t.encodage, sans_rel(t.encodage, VOC)
        a = int(np.flatnonzero(e.input_ids == VOC.ids["[REL]"])[0])
        n = len(e.input_ids) - len(s.input_ids)
        assert n >= 2 and not np.isin([VOC.ids["[REL]"], VOC.ids["[/REL]"]], s.input_ids).any()
        assert np.array_equal(s.input_ids[:a], e.input_ids[:a])
        assert np.array_equal(s.input_ids[a:], e.input_ids[a + n :])
        for c in ("fin_prop", "pos_mention", "pos_nombre"):
            assert np.array_equal(s.input_ids[getattr(s, c)], e.input_ids[getattr(e, c)])
            assert np.array_equal(s.name_idx[getattr(s, c)], e.name_idx[getattr(e, c)])


@pytest.mark.parametrize("attn", ["sdpa", "eager"])
def test_delta_nul_egale_a0(tirages, attn):
    """δ = 0 : A1 calcule exactement A0 (mêmes poids) ; le masque causal et les cases vides
    du crochet sont ceux du modèle de base."""
    encs = [sans_rel(t.encodage, VOC) for t in tirages]
    a0 = ModeleA0(_tronc(0, attn), VOC).eval()
    a1 = ModeleA1(_tronc(0, attn), VOC).eval()
    a1.load_state_dict(a0.state_dict(), strict=False)
    with torch.no_grad():
        for x, y in zip(a0.lot(encs), a1.lot(encs), strict=True):
            fini = torch.isfinite(x.logits)
            assert torch.equal(fini, torch.isfinite(y.logits))
            assert torch.allclose(x.logits[fini], y.logits[fini], atol=1e-5)
            assert torch.allclose(x.selection, y.selection, atol=1e-5)


def test_delta_appris_et_lot(tirages):
    """δ reçoit un gradient ; un lot complété à droite donne les sorties d'un par un."""
    encs = [sans_rel(t.encodage, VOC) for t in tirages]
    m = ModeleA1(_tronc(), VOC).eval()
    with torch.no_grad():
        m.delta.normal_()
        seuls = [m.lot([e])[0] for e in encs]
        a0 = ModeleA0(_tronc(), VOC).eval()
        a0.load_state_dict(m.state_dict(), strict=False)
        assert not torch.allclose(a0.lot(encs[:1])[0].selection, seuls[0].selection, atol=1e-3)
    for x, y in zip(seuls, m.lot(encs), strict=True):
        fini = torch.isfinite(x.logits)
        assert torch.allclose(x.logits[fini], y.logits[fini], atol=1e-4)
    m.train()
    m.delta.data.zero_()  # départ à zéro : le gradient passe quand même
    s = m(encs[0])
    perte(s, encs[0], tirages[0].exemple.justificatives)["total"].backward()
    assert m.delta.grad is not None and m.delta.grad.abs().sum() > 0
    assert m.etat.relations is None  # remis à None après la passe


def test_depuis_a0_et_optimiseur(tmp_path):
    a0 = ModeleA0(_tronc(0), VOC)
    for p in a0.parameters():
        if p.requires_grad:
            p.data.normal_()
    sauver(tmp_path / "a0.pt", a0, torch.optim.SGD(a0.parameters(), 0.1), None, 7)
    a1 = ModeleA1(_tronc(1), VOC)
    assert depuis_a0(a1, tmp_path / "a0.pt") == 7
    p0, p1 = poids_entraines(a0), poids_entraines(a1)
    assert set(p1) - set(p0) == {"delta"} and not p1["delta"].any()
    assert all(torch.equal(p0[n], p1[n]) for n in p0)
    groupes = optimiseur(a1).param_groups
    assert [g["weight_decay"] for g in groupes] == [0.01, 0.01, 0.0]
    assert groupes[2]["params"] == [a1.delta]
