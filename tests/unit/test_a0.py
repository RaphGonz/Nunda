"""Prototype A0 (SPEC.md §9) et perte du §13, sur un petit tronc LLaMA tiré au hasard
(même architecture que SmolLM2), avec LoRA, sur CPU."""

import dataclasses
import zlib

import numpy as np
import pytest
import torch

from ccm.anonymize.encode import Vocabulaire
from ccm.config import load_config
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.grammar.lexicon import LEXIQUE_COMPLET
from ccm.model.a0 import ModeleA0, Sortie, avec_lora, groupes, perte
from ccm.train.a0 import entrainer
from ccm.train.chargeur import Chargeur, SourceSynthetique

CFG = load_config("ingest")
WCFG = load_config("worldgen")
TAILLE = 1000
VOC = Vocabulaire(load_config("model_a0"), CFG, TAILLE)


def decouper(t):
    return [zlib.crc32(m.encode()) % TAILLE for m in t.split()]


def _modele(graine=0):
    from transformers import LlamaConfig, LlamaModel

    torch.manual_seed(graine)
    cfg = LlamaConfig(vocab_size=TAILLE, hidden_size=32, intermediate_size=64,
                      num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                      max_position_embeddings=8192)  # fmt: skip
    return ModeleA0(avec_lora(LlamaModel(cfg)), VOC)


@pytest.fixture(scope="module")
def tirages():
    d = rediger_dossier(generer_monde(0, "entrainement", WCFG, frozenset()), WCFG)
    src = SourceSynthetique([(d, poser_questions(d, WCFG))], CFG)
    ch = Chargeur({"synthetique": src}, load_config("finetune").chargeur, CFG,
                  load_config("search"), load_config("grammar"), VOC, decouper)  # fmt: skip
    out = [t for t in ch.epoque(0, 12) if t.genre == "normal"]
    assert any((t.encodage.cible >= len(LEXIQUE_COMPLET)).any() for t in out)
    return out[:4]


def test_formes_et_gradients(tirages):
    m = _modele()
    t = tirages[0]
    e = t.encodage
    s = m(e)
    assert s.logits.shape == (len(e.cible), len(e.espace))
    assert s.selection.shape == (len(e.fin_prop),)
    p = perte(s, e, t.exemple.justificatives)
    assert torch.isfinite(p["total"])
    p["total"].backward()
    # LoRA, table des jetons nouveaux, W_in (pointeurs de la référence) reçoivent un gradient.
    assert m.nouveaux.weight.grad.abs().sum() > 0
    assert m.w_in.weight.grad.abs().sum() > 0
    lora = [p for n, p in m.tronc.named_parameters() if "lora_B" in n]
    assert lora and all(p.grad is not None for p in lora)
    base = [p for n, p in m.tronc.named_parameters() if "lora" not in n]
    assert not any(p.requires_grad for p in base)


def test_pointeur_de_nom(tirages):
    """Pas de mention : −log de la somme des probabilités des mentions du même nom."""
    t = tirages[0]
    e = t.encodage
    g = groupes(e)
    debut = len(e.espace) - len(e.pos_mention)
    noms = e.name_idx[e.pos_mention]
    nom = next(n for n in noms if (noms == n).sum() > 1)  # un nom à plusieurs mentions
    c = debut + int((noms == nom).argmax())
    masque = torch.rand(len(e.espace), generator=torch.Generator().manual_seed(0)) < 0.7
    masque[c] = True
    e = dataclasses.replace(e, cible=np.array([c]), masque=masque.numpy()[None])
    logits = torch.randn(1, len(e.espace)).masked_fill(~masque, float("-inf"))
    s = Sortie(logits, torch.zeros(len(e.fin_prop)))
    p = torch.softmax(logits[0], -1)
    attendu = -torch.log(p[(g == g[c]) & masque].sum())
    assert ((g == g[c]) & masque).sum() >= 1 and (g[debut:] == g[c]).sum() > 1
    torch.testing.assert_close(perte(s, e, [])["actions"], attendu)


def test_surapprentissage(tirages):
    m = _modele()
    pertes = entrainer(m, tirages, 60, accumulation=len(tirages), lr_lora=2e-3, lr_nouveaux=1e-2)
    assert pertes[-1] < 0.3 * pertes[0], pertes[::10]


def test_point_de_controle(tirages, tmp_path):
    """§13 : un point de contrôle se recharge (mêmes pertes) et la reprise suit le même
    chemin que l'entraînement sans arrêt."""
    from ccm.model.a0 import optimiseur
    from ccm.train.a0 import ordonnanceur, pertes_eval, recharger, sauver

    def neuf(graine):
        m = _modele(graine)
        o = optimiseur(m)
        return m, o, ordonnanceur(o, 4)

    m, o, s = neuf(0)
    entrainer(m, tirages, 3, 2, opt=o, sched=s)
    sauver(tmp_path / "pc.pt", m, o, s, 3)
    torch.manual_seed(5)
    suite = entrainer(m, tirages, 2, 2, opt=o, sched=s, debut=3)

    m2, o2, s2 = neuf(1)
    m2.load_state_dict({k: v for k, v in _modele(0).state_dict().items()
                        if "lora" not in k and "tronc" in k}, strict=False)  # fmt: skip
    assert recharger(tmp_path / "pc.pt", m2, o2, s2) == 3
    torch.manual_seed(5)
    assert entrainer(m2, tirages, 2, 2, opt=o2, sched=s2, debut=3) == pytest.approx(suite, abs=1e-5)
    assert pertes_eval(m2, tirages) == pytest.approx(pertes_eval(m, tirages), abs=1e-6)


def test_perte_sans_proposition(tirages):
    """Contexte vide (abstention, P = 0) : la perte de sélection vaut 0, pas NaN."""
    t = tirages[0]
    s = _modele()(t.encodage)
    p = perte(Sortie(s.logits, s.selection[:0]), t.encodage, [])
    assert p["selection"].item() == 0 and torch.isfinite(p["total"])
