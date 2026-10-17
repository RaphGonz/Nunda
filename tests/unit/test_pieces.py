import hashlib
import re
from collections import Counter, defaultdict
from datetime import date, time
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ccm.config import load_config
from ccm.data.worldgen import controle
from ccm.data.worldgen.corpus import ecrire_corpus, produire_dossier
from ccm.data.worldgen.monde import EXCLUS_WIKIDATA, charger_exclusion, generer_monde
from ccm.data.worldgen.pdf import rendre_pdf
from ccm.data.worldgen.pieces import (
    Fait,
    ecrire_date,
    ecrire_heure,
    ecrire_montant,
    gabarits,
    rediger_dossier,
)

CFG = load_config("worldgen")
R = CFG.redaction
GRAINE = {"entrainement": 0, "test": 2_000_000}


def dossier(i, reservoir="entrainement"):
    return rediger_dossier(generer_monde(GRAINE[reservoir] + i, reservoir, CFG, frozenset()), CFG)


@pytest.fixture(scope="module")
def echantillon():
    return {res: [dossier(i, res) for i in range(300)] for res in GRAINE}


@pytest.mark.parametrize("reservoir", list(GRAINE))
def test_controle_passe_a_100_pourcent(reservoir):
    """Seuil de phase 1 : aucune pièce rejetée (noms, nombres, dates, PDF)."""
    for i in range(40):
        d, pdfs, erreurs = produire_dossier(GRAINE[reservoir] + i, reservoir, CFG, frozenset())
        assert erreurs == []
        assert len(pdfs) == len(d.pieces)
        assert R.pieces[0] <= len(d.pieces) <= R.pieces[1]


def test_surnom_en_debut_de_ligne():
    """Régression : la majuscule de début de ligne ne touche pas un nom (« le Chat »)."""
    exclus = charger_exclusion(EXCLUS_WIKIDATA)
    d, _, erreurs = produire_dossier(1862, "entrainement", CFG, exclus)
    assert erreurs == []
    debuts = [x for p in d.pieces for x in p.lignes if x.faits and x.faits[0].debut == 0]
    assert any(x.texte.startswith("le Chat") for x in debuts)


def test_invariants_des_pieces(echantillon):
    for d in echantillon["entrainement"] + echantillon["test"]:
        assert d.pieces[0].type and [p.id for p in d.pieces] == [
            f"P{k + 1:02d}" for k in range(len(d.pieces))
        ]
        assert "RAPPORT" in {p.type for p in d.pieces}
        couverts = {e for p in d.pieces for e in p.evenements}
        assert couverts == {e.id for e in d.monde.evenements}
        for p in d.pieces:
            assert p.evenements
            assert all(
                d.monde.evenements[e].type in R.types_par_piece[p.type] for e in p.evenements
            )
            assert all(d.monde.evenements[e].date < p.date for e in p.evenements)
            if p.type == "PV_AUDITION":
                parts = {i for e in p.evenements for i in d.monde.evenements[e].participants}
                assert p.locuteur not in parts


def test_meme_graine_memes_octets():
    a = produire_dossier(5, "entrainement", CFG, frozenset())
    b = produire_dossier(5, "entrainement", CFG, frozenset())
    assert a[0].model_dump_json() == b[0].model_dump_json()
    assert a[1] == b[1]
    assert a[1] != produire_dossier(6, "entrainement", CFG, frozenset())[1]


def test_corpus_memes_fichiers(tmp_path):
    def empreintes(sortie):
        ecrire_corpus(CFG, frozenset(), sortie, ["validation", "test"], limite=2, processus=2)
        return {
            f.relative_to(sortie).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(sortie.rglob("*"))
            if f.is_file()
        }

    a, b = empreintes(tmp_path / "a"), empreintes(tmp_path / "b")
    assert a == b
    assert sum(k.endswith(".pdf") for k in a) >= 4 * R.pieces[0]
    assert sum(k.endswith("verite.json") for k in a) == 4


def _textes(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _textes(v)
    else:
        for v in x:
            yield from _textes(v)


def test_gabarits_de_test_distincts():
    """SPEC.md §12 : gabarits différents pour le test."""

    def literaux(res):
        return {t for t in _textes(gabarits(res)) if re.sub(r"\{\w+\}", "", t).strip()}

    assert not literaux("entrainement") & literaux("test")


def test_gabarits_sans_chiffre_ni_mois():
    for res in GRAINE:
        for t in _textes(gabarits(res)):
            fixe = re.sub(r"\{\w+\}", " ", t)
            assert not re.search(r"\d", fixe), t
            assert not set(fixe.lower().split()) & set(controle.MOIS), t


@pytest.mark.parametrize("reservoir", list(GRAINE))
def test_au_moins_cinq_formulations(reservoir, echantillon):
    """Au moins 5 formulations par type de fait et par type de pièce (SPEC.md §12)."""
    g = gabarits(reservoir)
    for t, types in R.types_par_piece.items():
        for ev in types:
            if t in g["cadres"]:
                simples = [n for n in g["noyaux"][ev] if "{B}" not in n]
                assert len(g["cadres"][t]) * len(simples) >= 5, (t, ev)
                assert len(simples) >= 5, (t, ev)
    for cle in ("parties", "prix", "fait"):
        assert len(g["pieces"]["CONTRAT"][cle]) >= 5
    assert len(g["pieces"]["RELEVE"]["libelles"]) >= 5
    for cle in ("identite", "alias"):
        assert len(g["pieces"]["PV_AUDITION"][cle]) >= 5

    # Dans le corpus : formulations distinctes vues par (type d'événement, type de pièce).
    vues = defaultdict(set)
    for d in echantillon[reservoir]:
        for p in d.pieces:
            for ligne in p.lignes:
                if ligne.evenement is not None:
                    ev = d.monde.evenements[ligne.evenement].type
                    vues[ev, p.type].add(ligne.gabarit)
    attendues = {(ev, t) for t, types in R.types_par_piece.items() for ev in types}
    assert set(vues) == attendues
    assert all(len(v) >= 5 for v in vues.values()), {k: len(v) for k, v in vues.items()}


def test_toutes_les_formes_d_un_nom(echantillon):
    formes, dit = Counter(), 0
    for d in echantillon["entrainement"]:
        for p in d.pieces:
            for ligne in p.lignes:
                formes.update(f.forme for f in ligne.faits if f.genre in ("PER", "ORG"))
                dit += ", dit " in ligne.texte
    attendues = {"COMPLET", "NOM_PRENOM", "INITIALES", "NOM_SEUL", "TITRE_NOM", "SURNOM", "COURT"}
    assert attendues <= set(formes), formes
    assert dit > 0


def test_versions_contradictoires(echantillon):
    dossiers = echantillon["entrainement"] + echantillon["test"]
    avec = [d for d in dossiers if d.conflit]
    assert abs(len(avec) / len(dossiers) - R.part_contradiction) < 0.05
    champs = Counter()
    for d in avec:
        c, v = d.conflit, d.variante
        e = d.monde.evenements[c.evenement]
        champs[c.champ] += 1
        differents = {
            k for k in ("heure", "montants", "participants") if getattr(e, k) != getattr(v, k)
        }
        assert differents == {
            {"HEURE": "heure", "MONTANT": "montants", "PERSONNE": "participants"}[c.champ]
        }
        p1, p2 = (next(p for p in d.pieces if p.id == i) for i in c.pieces)
        assert p1.type == p2.type == "PV_AUDITION" and p1.locuteur != p2.locuteur
        assert {p1.locuteur, p2.locuteur}.isdisjoint(v.participants)
        versions = {
            p.id: {x.version for x in p.lignes if x.evenement == c.evenement} for p in (p1, p2)
        }
        assert versions == {p1.id: {0}, p2.id: {1}}
        assert all(x.version == 0 for p in d.pieces if p is not p2 for x in p.lignes)
        # Le champ changé est écrit par les deux témoins : le conflit se lit dans le texte.
        genre = {"HEURE": "HEURE", "MONTANT": "NUM", "PERSONNE": "PER"}[c.champ]
        for p in (p1, p2):
            assert any(
                f.genre == genre for x in p.lignes if x.evenement == c.evenement for f in x.faits
            )
    assert set(champs) == set(R.champs_contradiction)


# --- Le contrôle refuse ce qui n'est pas déclaré ---------------------------------------


def _premiere(d, pred):
    for p in d.pieces:
        for k, ligne in enumerate(p.lignes):
            if pred(ligne):
                return p, k, ligne
    raise LookupError


def _remplacer(p, k, ligne):
    lignes = list(p.lignes)
    lignes[k] = ligne
    return p.model_copy(update=dict(lignes=tuple(lignes)))


def _erreurs(d, p, k, ligne):
    return controle.controler_piece(d, _remplacer(p, k, ligne))


def test_sondes_du_controle():
    d = dossier(3)
    p, k, ligne = _premiere(d, lambda x: x.evenement is not None and len(x.faits) >= 3)
    assert controle.controler_piece(d, p) == []

    # Chiffre, mois, nom du monde, mot à majuscule ajoutés hors des faits.
    nom = d.monde.personnes[0].nom
    for ajout in (" 12", " en mars", f" avec {nom}", " Zorglub"):
        assert _erreurs(d, p, k, ligne.model_copy(update=dict(texte=ligne.texte + ajout)))

    # Personne déclarée qui n'est pas un participant de l'événement.
    ev = d.monde.evenements[ligne.evenement]
    f = next(f for f in ligne.faits if f.genre == "PER")
    autre = next(x for x in d.monde.personnes if x.id not in ev.participants)
    faits = tuple(x.model_copy(update=dict(entite=autre.id)) if x is f else x for x in ligne.faits)
    assert _erreurs(d, p, k, ligne.model_copy(update=dict(faits=faits)))

    # Valeur déclarée juste, surface fausse ; fait retiré (son texte reste non déclaré).
    f = next(f for f in ligne.faits if f.genre == "DATE")
    faux = ligne.texte[: f.debut] + "31 février 2020" + ligne.texte[f.fin :]
    assert _erreurs(d, p, k, ligne.model_copy(update=dict(texte=faux)))
    faits = tuple(x for x in ligne.faits if x is not f)
    assert _erreurs(d, p, k, ligne.model_copy(update=dict(faits=faits)))

    # Version contradictoire déclarée comme version du monde : la valeur ne s'y trouve pas.
    dc = next(x for x in (dossier(i) for i in range(50)) if x.conflit)
    p2 = next(x for x in dc.pieces if x.id == dc.conflit.pieces[1])
    k2 = next(j for j, x in enumerate(p2.lignes) if x.version == 1)
    assert controle.controler_piece(dc, p2) == []
    assert _erreurs(dc, p2, k2, p2.lignes[k2].model_copy(update=dict(version=0)))


def test_sonde_du_pdf():
    d = dossier(4)
    p = d.pieces[0]
    pdf = rendre_pdf(p, R.pdf)
    assert controle.controler_pdf(pdf, p) == []
    ligne = p.lignes[-1].model_copy(update=dict(texte=p.lignes[-1].texte + " ajouté"))
    assert controle.controler_pdf(pdf, _remplacer(p, len(p.lignes) - 1, ligne))


def test_fait_type():
    with pytest.raises(ValueError):
        Fait(debut=0, fin=1, surface="x", genre="NOM")


# --- Les analyseurs du contrôle relisent ce que le rédacteur écrit ---------------------


@given(st.integers(1, 10**9), st.randoms(use_true_random=False))
def test_relire_montant(centimes, rng):
    v = Decimal(centimes) / 100
    assert controle.lire_montant(ecrire_montant(v, rng)) == v


@given(st.dates(date(1900, 1, 1), date(2100, 12, 31)), st.randoms(use_true_random=False))
def test_relire_date(d, rng):
    assert controle.lire_date(ecrire_date(d, rng)) == d


@given(st.times(), st.randoms(use_true_random=False))
def test_relire_heure(h, rng):
    h = time(h.hour, h.minute)
    assert controle.lire_heure(ecrire_heure(h, rng)) == h
