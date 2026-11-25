"""Canaris (SPEC.md §14) : comptes, langues, noms inventés, documents distincts, fins."""

from collections import Counter

import pytest

from ccm.config import load_config
from ccm.data import canaries
from ccm.data.worldgen.monde import EXCLUS_WIKIDATA, charger_exclusion, cle
from ccm.ner import detectors
from ccm.ner.union import detecter

CFG = load_config("pretrain").corpus
C = CFG.canaris_cfg
ICFG = load_config("ingest")
LEXIQUES = all((detectors.RACINE / f"{d}.dic").exists() for d in C.lexiques.values())
avec_lexiques = pytest.mark.skipif(not LEXIQUES, reason="lexiques absents : `ccm modeles`")
FINS = {"fr": [f"fin{i:04d}" for i in range(C.fins)], "en": [f"end{i:04d}" for i in range(C.fins)]}
EXCLUS = charger_exclusion(EXCLUS_WIKIDATA)


@pytest.fixture(scope="module")
def liste():
    return canaries.generer(C, FINS, EXCLUS, CFG.graine)


def test_comptes(liste):
    assert len(liste) == 600
    comptes = Counter((c["genre"], c["frequence"]) for c in liste)
    assert comptes == {(g, f): 100 for g in canaries.GENRES for f in (1, 10, 100)}
    langues = Counter((c["genre"], c["frequence"], c["langue"]) for c in liste)
    assert all(langues[(g, f, "fr")] == 70 and langues[(g, f, "en")] == 30
               for g in canaries.GENRES for f in (1, 10, 100))  # fmt: skip


def test_noms_et_phrases(liste):
    noms = [cle(c["nom"]) for c in liste]
    assert len(set(noms)) == len(noms)
    assert not set(noms) & EXCLUS
    for c in liste:
        assert c["fin"] in c["fins"] and len(c["fins"]) == C.fins
        assert c["phrase"] == f"{c['prefixe']}{c['fin']}." and c["nom"] in c["phrase"]
    assert canaries.generer(C, FINS, EXCLUS, CFG.graine) == liste  # même graine


def test_documents_distincts(liste):
    docs = [(f"d{i}", "fr" if i % 10 < 7 else "en") for i in range(12_000)]
    langue = dict(docs)
    cible = canaries.choisir(docs, liste, "naturel", 0)
    vus = [i for c in liste if c["genre"] == "naturel" for i in c["documents"]]
    assert len(vus) == len(set(vus)) == 100 * 111 == len(cible)
    for c in liste:
        if c["genre"] == "naturel":
            assert len(c["documents"]) == c["frequence"]
            assert {langue[i] for i in c["documents"]} == {c["langue"]}
    with pytest.raises(ValueError):
        canaries.choisir(docs[:100], liste, "force", 0)


@avec_lexiques
def test_fins_du_lexique_hors_des_zones():
    fins = {lg: canaries.fins_candidates(detectors.RACINE / f"{d}.dic", lg, C, CFG.graine)
            for lg, d in C.lexiques.items()}  # fmt: skip
    for fs in fins.values():
        assert len(set(fs)) == C.fins and all(f.isalpha() and f.islower() for f in fs)
    liste = canaries.generer(C, fins, EXCLUS, CFG.graine)
    det = ICFG.detection.model_copy(update={"detecteurs": ("regle", "majuscules")})
    cfg = ICFG.model_copy(update={"detection": det})
    phrases = [c["phrase"] for c in liste]
    for c, zs in zip(liste, detecter(phrases, cfg), strict=True):
        debut = len(c["prefixe"])
        assert not any(z.debut < debut + len(c["fin"]) and debut < z.fin for z in zs), c["id"]


@pytest.mark.couteux
@avec_lexiques
def test_fins_hors_des_zones_chaine_fr_complete():
    """Vraie chaîne fr (GLiNER, spaCy, règles, majuscules) sur les canaris français."""
    fins = {lg: canaries.fins_candidates(detectors.RACINE / f"{d}.dic", lg, C, CFG.graine)
            for lg, d in C.lexiques.items()}  # fmt: skip
    liste = [c for c in canaries.generer(C, fins, EXCLUS, CFG.graine) if c["langue"] == "fr"]
    zones = detecter([c["phrase"] for c in liste], ICFG)
    touchees = [c["id"] for c, zs in zip(liste, zones, strict=True)
                if any(z.fin > len(c["prefixe"]) for z in zs)]  # fmt: skip
    assert not touchees
