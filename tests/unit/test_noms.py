"""Étape 5 : détection des noms (SPEC.md §6) : détecteurs, union, limites, propagation,
messages de l'utilisateur."""

from pathlib import Path

import pytest

from ccm.config import load_config
from ccm.ner import detectors
from ccm.ner.detectors import Zone, d3_regles, d4_majuscules
from ccm.ner.propagate import detecter_message, ecrire_mentions, propager
from ccm.ner.union import detecter, en_tete_tableau, limites, unir
from ccm.schema import Detecteur, TypeNom, ouvrir_stock

CFG = load_config("ingest")
LEXIQUES = all((detectors.RACINE / f"{c}.dic").exists() for c in CFG.detection.lexiques)
GLINER = (detectors.RACINE / CFG.detection.gliner.modele / "model.safetensors").exists()
avec_lexiques = pytest.mark.skipif(not LEXIQUES, reason="lexiques absents : `ccm modeles`")
avec_gliner = pytest.mark.skipif(not GLINER, reason="GLiNER absent : `ccm modeles`")
G, S = frozenset({Detecteur.GLINER}), frozenset({Detecteur.SPACY})


def sans_modeles(*detecteurs):
    det = CFG.detection.model_copy(update={"detecteurs": detecteurs})
    return CFG.model_copy(update={"detection": det})


def surfaces(texte, zones):
    return [(texte[z.debut : z.fin], str(z.type)) for z in zones]


def test_union_chevauchement_et_priorite():
    zs = unir(
        [Zone(0, 6, TypeNom.ORG, G), Zone(3, 12, TypeNom.PER, S), Zone(20, 25, TypeNom.LIEU, G)]
    )
    assert zs == [Zone(0, 12, TypeNom.PER, G | S), Zone(20, 25, TypeNom.LIEU, G)]
    assert unir([Zone(0, 4, TypeNom.AUTRE, G), Zone(0, 4, TypeNom.REF, S)])[0].type == TypeNom.REF


def test_limites_particules_titres_et_majuscules():
    t = "Jean de La Fontaine et M. Dupont, Mme, 35027,14 euros."
    zs = [
        Zone(0, 4, TypeNom.PER, G),  # Jean
        Zone(8, 19, TypeNom.AUTRE, S),  # La Fontaine
        Zone(23, 32, TypeNom.PER, G),  # M. Dupont
        Zone(34, 37, TypeNom.PER, S),  # Mme seul
        Zone(39, 47, TypeNom.AUTRE, S),  # 35027,14 : aucune majuscule
    ]
    assert surfaces(t, limites(t, zs, CFG.noms)) == [
        ("Jean de La Fontaine", "PER"),
        ("Dupont", "PER"),
    ]
    # Deux noms reliés par « et » restent deux noms ; une référence ne fusionne pas.
    t = "Dupont et Martin, PV 2025/123"
    zs = [Zone(0, 6, TypeNom.PER, G), Zone(10, 16, TypeNom.PER, G), Zone(21, 29, TypeNom.REF, G)]
    assert len(limites(t, zs, CFG.noms)) == 3


def test_limites_cellules_et_bords_sans_lettre():
    t = "7 mai 2024 | SA Mon | 39 625,13 euros | au 12 rue Haute, Ly le 3/05/2024"
    org, lieu = t.index("SA Mon"), t.index("12 rue")
    zs = [Zone(0, org + 6, TypeNom.ORG, G), Zone(lieu, len(t), TypeNom.LIEU, S)]
    # « 7 mai 2024 » perd ses bords sans lettre ; « mai » seul, sans majuscule, sort.
    assert surfaces(t, limites(t, zs, CFG.noms)) == [
        ("SA Mon", "ORG"),
        ("12 rue Haute, Ly le", "LIEU"),
    ]
    # Un numéro de rue reste dans la zone, quel que soit son type ; une date en sort.
    t = "au 103 rue de la Poste, le 13 mars 2024 Datorien Corin"
    zs = [Zone(3, 22, TypeNom.ORG, G), Zone(t.index("13"), len(t), TypeNom.PER, G)]
    assert surfaces(t, limites(t, zs, CFG.noms, CFG.nombres.mois)) == [
        ("103 rue de la Poste", "ORG"),
        ("Datorien Corin", "PER"),
    ]


def test_d3_references():
    t = (
        "Vu l'art. 1240 et l'article L. 121-1, tél. 06 12 34 56 78, jean.dupont@exemple.fr, "
        "IBAN FR76 3000 6000 0112 3456 7890 189, SIREN : 123 456 789, AB-123-CD, "
        "https://www.exemple.fr/a, dossier n° 2025/00123 ; montant : 123 456 789 euros."
    )
    refs = [t[z.debut : z.fin] for z in d3_regles(t, CFG.detection, CFG.nombres)]
    for attendu in (
        "art. 1240",
        "06 12 34 56 78",
        "jean.dupont@exemple.fr",
        "AB-123-CD",
        "https://www.exemple.fr/a",
    ):
        assert any(attendu in r for r in refs), attendu
    assert any("123 456 789" in r and "SIREN" in r for r in refs)
    assert not any("euros" in r or r == "123 456 789" for r in refs)


@avec_lexiques
def test_d4_majuscules():
    t = "Je confirme qu'Elodie Bamier et RIBORIER Belcorel ont vu S.M. au Tribunal."
    assert surfaces(t, d4_majuscules(t, CFG.detection)) == [
        ("Elodie Bamier", "AUTRE"),
        ("RIBORIER Belcorel", "AUTRE"),
        ("S.M.", "AUTRE"),
    ]
    t = "PROCÈS-VERBAL D'AUDITION. Transfert Import-Export."
    assert d4_majuscules(t, CFG.detection) == []


def test_propagation():
    textes = [
        "Témoin : Belcorel Riborier.",
        "Vu Belcorel.",
        "Belcorel et Belcorelle, Belcorel Riborier.",
    ]
    zones = [[Zone(9, 26, TypeNom.PER, G)], [Zone(3, 11, TypeNom.AUTRE, S)], []]
    out = propager(textes, zones, 2)
    assert surfaces(textes[2], out[2]) == [("Belcorel", "AUTRE"), ("Belcorel Riborier", "PER")]
    assert {d for z in out[2] for d in z.detecteurs} == {Detecteur.PROPAGATION}
    assert out[:2] == zones[:2]


@avec_lexiques
def test_message_utilisateur_sans_casse(tmp_path):
    cfg = sans_modeles("regle", "majuscules")
    con = ouvrir_stock(tmp_path / "s.sqlite")
    for i, texte, z in [
        (1, "Audition de Jean-Éloi Dupont.", (12, 28)),
        (2, "Dupont est là.", (0, 6)),
    ]:
        con.execute("INSERT INTO proposition (prop_id, texte) VALUES (?, ?)", (i, texte))
        ecrire_mentions(con, i, texte, [Zone(*z, TypeNom.PER, G)], cfg)
    m = "qu'a dit jean eloi dupont ? et DUPONT ?"
    assert surfaces(m, detecter_message(m, con, cfg)) == [
        ("jean eloi dupont", "PER"),
        ("DUPONT", "PER"),
    ]


@avec_lexiques
def test_message_utilisateur_mot_d_un_nom(tmp_path):
    cfg = sans_modeles("regle", "majuscules")
    con = ouvrir_stock(tmp_path / "s.sqlite")
    texte = "Audition de M. Jean-Éloi Dupont, de la Société Gérard."
    con.execute("INSERT INTO proposition (prop_id, texte) VALUES (1, ?)", (texte,))
    ecrire_mentions(
        con, 1, texte, [Zone(15, 31, TypeNom.PER, G), Zone(39, 53, TypeNom.ORG, G)], cfg
    )
    m = "et eloi ? dupont ? la société ? gerard ?"
    assert surfaces(m, detecter_message(m, con, cfg)) == [
        ("eloi", "PER"),
        ("dupont", "PER"),
        ("gerard", "ORG"),
    ]


@avec_lexiques
def test_detecter_sans_gliner_ni_spacy():
    cfg = sans_modeles("regle", "majuscules")
    t = "Le 3 mai, M. RIBORIER Belcorel a viré 300 euros (n° 2025/123)."
    assert surfaces(t, detecter([t], cfg)[0]) == [
        ("RIBORIER Belcorel", "AUTRE"),
        ("n° 2025/123", "REF"),
    ]


@avec_gliner
@avec_lexiques
def test_detecter_quatre_detecteurs():
    t = "Je confirme qu'Elodie Bamier a paraphé un contrat avec la SARL Delcoron à Lyon."
    s = surfaces(t, detecter([t], CFG)[0])
    assert ("Elodie Bamier", "PER") in s
    assert ("SARL Delcoron", "ORG") in s
    assert ("Lyon", "LIEU") in s


@avec_lexiques
def test_en_tete_tableau():
    lex = CFG.detection.lexiques
    assert en_tete_tableau("Date | Libellé | Montant", lex)
    assert en_tete_tableau("Date de valeur | Opération | Somme", lex)
    assert not en_tete_tableau("Date Libellé Montant", lex)  # pas un tableau
    assert not en_tete_tableau("03/05/2024 | Virement Delcoron | 300,00", lex)
    assert not en_tete_tableau("Nom | Delcoron", lex)


@avec_gliner
@avec_lexiques
def test_detecter_en_tete_tableau_sans_nom():
    ts = ["Date | Libellé | Montant", "Date | Opération | Montant"]
    assert detecter(ts, CFG) == [[], []]


def test_modeles_lus_sur_le_disque():
    assert not Path(CFG.detection.gliner.modele).is_absolute()


def test_d4_mot_a_nombreux_tirets():
    """Chaîne d'acides aminés : spylls essayait toutes les coupes aux tirets (bloqué 9 h)."""
    mot = "Ser-" + "-".join("tyr ser met glu his phe arg try gly lys".split() * 4)
    t = f"La séquence {mot} est connue."
    assert surfaces(t, d4_majuscules(t, CFG.detection)) == [(mot, "AUTRE")]
