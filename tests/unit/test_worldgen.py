from collections import Counter
from decimal import Decimal

import pytest

from ccm.config import load_config
from ccm.data.worldgen import wikidata
from ccm.data.worldgen.monde import (
    EXCLUS_WIKIDATA,
    VERIFIES_WIKIDATA,
    Monde,
    charger_exclusion,
    cle,
    generer_monde,
    mondes_corpus,
    noms_du_monde,
    reservoir_de,
)

CFG = load_config("worldgen")


def monde(graine, reservoir="entrainement", exclus=frozenset()):
    return generer_monde(graine, reservoir, CFG, exclus)


def complet(p):
    return cle(f"{p.prenom} {p.nom}")


def verifier(m: Monde):
    """Invariants d'un monde (SPEC.md §12)."""
    for champ, n in [
        ("personnes", len(m.personnes)),
        ("societes", len(m.societes)),
        ("lieux", len(m.lieux)),
        ("evenements", len(m.evenements)),
    ]:
        lo, hi = getattr(CFG, champ)
        assert lo <= n <= hi, champ
    assert all(p.role in CFG.roles for p in m.personnes)

    # Cas durs : présents si et seulement si tirés.
    surnoms = [p.surnom for p in m.personnes if p.surnom]
    assert len(surnoms) == (1 if m.cas.alias else 0)
    noms = Counter(cle(p.nom) for p in m.personnes)
    complets = Counter(complet(p) for p in m.personnes)
    assert sum(c - 1 for c in complets.values()) == (1 if m.cas.meme_nom_complet else 0)
    paires_famille = sum(c - 1 for c in noms.values()) - sum(c - 1 for c in complets.values())
    assert paires_famille == (1 if m.cas.meme_famille else 0)

    # Réservoir : chaque nom tiré vient du réservoir du monde.
    chaines = noms_du_monde(m)
    assert {p.nom for p in m.personnes} | {x.nom for x in m.societes} <= chaines
    for s in chaines:
        assert reservoir_de(s) == m.reservoir, s

    # Événements.
    dates = [e.date for e in m.evenements]
    assert CFG.debut <= min(dates) and max(dates) <= CFG.fin
    assert (max(dates) - min(dates)).days <= CFG.duree_dossier_jours
    assert [(e.date, e.heure) for e in m.evenements] == sorted(
        (e.date, e.heure) for e in m.evenements
    )
    for e in m.evenements:
        assert e.type in CFG.types_evenement
        assert 0 <= e.lieu < len(m.lieux)
        assert e.participants and all(0 <= i < len(m.personnes) for i in e.participants)
        assert len(set(e.participants)) == len(e.participants)
        assert bool(e.montants) == (e.type in CFG.types_avec_montant)
        assert bool(e.societes) == (e.type in CFG.types_avec_societe)
        assert all(0 <= i < len(m.societes) for i in e.societes)
        lo, hi = CFG.montant_centimes
        assert all(lo <= x * 100 <= hi and x == x.quantize(Decimal("0.01")) for x in e.montants)


@pytest.mark.parametrize("reservoir", ["entrainement", "test"])
def test_invariants(reservoir):
    for graine in range(300):
        verifier(monde(graine, reservoir))


def test_meme_graine_memes_octets():
    for graine in (0, 7, 123456789):
        assert monde(graine).model_dump_json() == monde(graine).model_dump_json()
    assert monde(1).model_dump_json() != monde(2).model_dump_json()


def test_graine_obligatoire():
    with pytest.raises(TypeError):
        generer_monde(reservoir="entrainement", cfg=CFG, exclus=frozenset())


def test_parts_des_cas_durs():
    n = 2000
    cas = [monde(g).cas for g in range(n)]
    for champ, attendu in [
        ("alias", CFG.part_alias),
        ("meme_famille", CFG.part_meme_famille),
        ("meme_nom_complet", CFG.part_meme_nom_complet),
    ]:
        part = sum(getattr(c, champ) for c in cas) / n
        assert abs(part - attendu) < 0.03, (champ, part)


def test_reservoirs_disjoints():
    def noms(reservoir):
        return {
            cle(s)
            for g in range(200)
            for p in monde(g, reservoir).personnes
            for s in (p.prenom, p.nom)
        }

    assert not noms("entrainement") & noms("test")


def test_exclusion_respectee(tmp_path):
    graines = range(100)
    vus = {complet(p) for g in graines for p in monde(g).personnes}
    fichier = tmp_path / "exclus.txt"
    # Casse, accents et tirets différents : la comparaison se fait sur la clé.
    lignes = [n.upper() for n in vus] + ["Jean-Pierre Dupont", ""]
    fichier.write_text("\n".join(lignes), encoding="utf-8")
    exclus = charger_exclusion(fichier)
    assert cle("JEAN PIERRE DUPONT") in exclus
    for g in graines:
        m = monde(g, exclus=exclus)
        assert not {complet(p) for p in m.personnes} & exclus
        verifier(m)


def test_cle():
    assert cle("  Jean-Pierre   LEFÈVRE ") == "jean pierre lefevre"
    assert cle("Ｊｅａｎ") == "jean"


def test_corpus_hors_liste_wikidata():
    """Chaque nom complet du corpus a été vérifié dans Wikidata et n'y est pas (SPEC.md §12).

    Échoue si les réservoirs ou la config changent sans relancer worldgen/wikidata.py.
    """
    verifies = set(VERIFIES_WIKIDATA.read_text(encoding="utf-8").splitlines())
    lignes = EXCLUS_WIKIDATA.read_text(encoding="utf-8").splitlines()
    assert lignes and all(lignes) and lignes == sorted(set(lignes))
    exclus = charger_exclusion(EXCLUS_WIKIDATA)
    parties = Counter()
    for partie, m in mondes_corpus(CFG, exclus):
        parties[partie] += 1
        assert not {complet(p) for p in m.personnes} & exclus
        assert {f"{p.prenom} {p.nom}" for p in m.personnes} <= verifies
    assert parties == {nom: p.dossiers for nom, p in CFG.corpus.items()}


def test_humains_par_lots(monkeypatch):
    lots = []

    def faux_sparql(valeurs, cfg):
        lots.append(valeurs)
        return {v for v in valeurs if v.startswith("Jean")}

    monkeypatch.setattr(wikidata, "_sparql", faux_sparql)
    monkeypatch.setattr(wikidata.time, "sleep", lambda s: None)
    noms = [f"Jean {i}" for i in range(CFG.wikidata_lot)] + ["Zoé Zorvin"]
    assert wikidata.humains(noms, CFG) == {f"Jean {i}" for i in range(CFG.wikidata_lot)}
    assert [len(x) for x in lots] == [CFG.wikidata_lot, 1]
