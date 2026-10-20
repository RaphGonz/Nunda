"""Ingestion, étapes 4, 6 et 7 (SPEC.md §5) : tableaux et champs, nombres et dates, doublons."""

import pymupdf
import pytest

from ccm.config import load_config
from ccm.ingest.dedup import dedoublonner
from ccm.ingest.numbers import nombres
from ccm.ingest.pipeline import ingerer_fichier, ingerer_fichiers
from ccm.ingest.segment import _champ
from ccm.schema import ouvrir_stock

CFG = load_config("ingest")
MARGE, PAS, TAILLE = 56, 14, 10.5


def pdf_tableau(chemin, avant, rangees, apres, rangees_page_2=()):
    """Paragraphes `avant`, un tableau tracé (une cellule par rectangle), `apres` ; des
    rangées de plus en tête d'une deuxième page."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = MARGE

    def texte(s):
        nonlocal y
        page.insert_text((MARGE, y + PAS - 3), s, fontsize=TAILLE)
        y += PAS + 6

    def tableau(rs):
        nonlocal y
        for r in rs:
            x = MARGE
            for c in r:
                page.draw_rect(pymupdf.Rect(x, y, x + 160, y + 24), width=0.5)
                page.insert_text((x + 4, y + 16), c, fontsize=TAILLE)
                x += 160
            y += 24
        y += 6

    for s in avant:
        texte(s)
    tableau(rangees)
    for s in apres:
        texte(s)
    if rangees_page_2:
        page = doc.new_page(width=595, height=842)
        y = MARGE
        tableau(rangees_page_2)
    doc.save(chemin)
    return chemin


def props(con):
    return con.execute("SELECT ordre, texte, genre FROM proposition ORDER BY prop_id").fetchall()


def depend(con):
    q = (
        "SELECT a.ordre, b.ordre FROM arete JOIN proposition a ON a.prop_id = src "
        "JOIN proposition b ON b.prop_id = dst WHERE type = 'DEPEND_DE' ORDER BY 1, 2"
    )
    return con.execute(q).fetchall()


def test_tableau_et_champs(tmp_path):
    rangees = [
        ["Date", "Libellé", "Montant"],
        ["7 décembre 2024", "Virement reçu", "1 250,00 euros"],
        ["8 décembre 2024", "Retrait", "300 euros"],
    ]
    chemin = pdf_tableau(
        tmp_path / "T1.pdf",
        ["RELEVÉ DE COMPTE", "Titulaire : SAS Martin", "Période : du 1er au 31 décembre 2024"],
        rangees,
        ["Le solde est créditeur ce mois-ci."],
        rangees_page_2=[["9 décembre 2024", "Frais", "12 euros"]],
    )
    con = ouvrir_stock(":memory:")
    ingerer_fichier(con, chemin, CFG)
    assert props(con) == [
        (0, "RELEVÉ DE COMPTE", "EN_TETE"),
        (1, "Titulaire : SAS Martin", "CHAMP"),
        (2, "Période : du 1er au 31 décembre 2024", "CHAMP"),
        (3, "Date | Libellé | Montant", "LIGNE_TABLEAU"),
        (4, "7 décembre 2024 | Virement reçu | 1 250,00 euros", "LIGNE_TABLEAU"),
        (5, "8 décembre 2024 | Retrait | 300 euros", "LIGNE_TABLEAU"),
        (6, "Le solde est créditeur ce mois-ci.", "PHRASE"),
        (7, "9 décembre 2024 | Frais | 12 euros", "LIGNE_TABLEAU"),
    ]
    # Lignes vers l'en-tête de leur tableau ; la phrase coupe le tableau.
    assert depend(con) == [(4, 3), (5, 3)]
    vals = con.execute(
        "SELECT surface, valeur, unite FROM nombre JOIN proposition USING (prop_id) "
        "WHERE ordre = 4 ORDER BY debut"
    ).fetchall()
    assert vals == [("7 décembre 2024", "2024-12-07", "date"), ("1 250,00 euros", "1250.00", "€")]


def test_tableau_coupe_par_la_page(tmp_path):
    chemin = pdf_tableau(
        tmp_path / "T2.pdf",
        ["RELEVÉ DE COMPTE"],
        [["Date", "Montant"], ["7 décembre 2024", "300 euros"]],
        [],
        rangees_page_2=[["8 décembre 2024", "12 euros"]],
    )
    con = ouvrir_stock(":memory:")
    ingerer_fichier(con, chemin, CFG)
    assert depend(con) == [(2, 1), (3, 1)]


def test_champ_mais_pas_question_ni_phrase_longue():
    c = CFG.segmentation
    assert _champ("Objet : votre demande de renseignements", c)
    assert _champ("Procès-verbal n° : 2025/44039", c)
    assert not _champ("Question : Où étiez-vous ?", c)
    assert not _champ("Réponse : Chez moi.", c)
    assert not _champ("Le témoin, entendu ce jour au commissariat central, déclare : rien.", c)


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("le 7 décembre 2024", [("7 décembre 2024", "DATE", "2024-12-07", "date", "JOUR")]),
        ("le 1er mars 2025", [("1er mars 2025", "DATE", "2025-03-01", "date", "JOUR")]),
        ("en Décembre 2024", [("Décembre 2024", "DATE", "2024-12", "date", "MOIS")]),
        ("le 27/06/2025", [("27/06/2025", "DATE", "2025-06-27", "date", "JOUR")]),
        ("en 2024,", [("2024", "DATE", "2024", "date", "ANNEE")]),
        ("le 31/02/2025", []),  # date impossible : rien
        ("à 21h59", [("21h59", "NUM", "1319", "heure du jour", None)]),
        ("vers 5 h 03", [("5 h 03", "NUM", "303", "heure du jour", None)]),
        ("à 03:04", [("03:04", "NUM", "184", "heure du jour", None)]),
        ("à 21 heures", [("21 heures", "NUM", "1260", "heure du jour", None)]),
        ("pendant 3 heures", [("3 heures", "NUM", "3", "heure", None)]),
        ("de 28 642,42 €", [("28 642,42 €", "NUM", "28642.42", "€", None)]),
        ("de 32729,53 euros", [("32729,53 euros", "NUM", "32729.53", "€", None)]),
        ("un débit de −150 €", [("−150 €", "NUM", "-150", "€", None)]),
        ("une hausse de 12,5 %", [("12,5 %", "NUM", "12.5", "%", None)]),
        ("trois mois plus tard", [("trois mois", "NUM", "3", "mois", None)]),
        (
            "quatre-vingt-dix-neuf kilomètres",
            [("quatre-vingt-dix-neuf kilomètres", "NUM", "99", "km", None)],
        ),
        (
            "deux mille cinq cents euros",
            [("deux mille cinq cents euros", "NUM", "2500", "€", None)],
        ),
        ("trois témoins", []),  # en lettres, sans unité : pas un nombre
        ("15 personnes", [("15", "NUM", "15", "", None)]),
        ("le 1er étage", []),
    ],
)
def test_nombres_et_dates(texte, attendu):
    lus = [
        (n.surface, str(n.genre), n.valeur, n.unite, n.precision and str(n.precision))
        for n in nombres(texte, CFG.nombres)
    ]
    assert lus == attendu


@pytest.mark.parametrize(
    "texte",
    [
        "PV n° 2025/40649",
        "Numéro de compte : 2025/40649",
        "l'article L. 121-1 du code",
        "l'art. 311-1",
        "tél. 06 12 34 56 78 ou +33 6 12 34 56 78",
        "IBAN FR76 3000 6000 0112 3456 7890 189",
        "le véhicule AB-123-CD",
    ],
)
def test_references_jamais_des_nombres(texte):
    assert nombres(texte, CFG.nombres) == []


def test_zones_exclues():
    t = "au 77 rue de la Fontaine le 7 décembre 2024"
    assert [n.surface for n in nombres(t, CFG.nombres)] == ["77", "7 décembre 2024"]
    assert [n.surface for n in nombres(t, CFG.nombres, [(3, 24)])] == ["7 décembre 2024"]


def _stock(textes_confs):
    con = ouvrir_stock(":memory:")
    con.execute("INSERT INTO piece (piece_id) VALUES ('P')")
    con.executemany(
        "INSERT INTO proposition (piece_id, ordre, texte, ocr_conf) VALUES ('P', ?, ?, ?)",
        [(k, t, c) for k, (t, c) in enumerate(textes_confs)],
    )
    return con


def test_doublons_exacts_et_quasi_copies():
    longue = " ".join(f"mot{k}" for k in range(60))
    con = _stock(
        [
            ("Le témoin  signe le procès-verbal.", 0.8),  # 1
            ("le témoin signe le PROCÈS-VERBAL.", 0.95),  # 2 : copie exacte normalisée, gardée
            (longue, 1.0),  # 3
            (longue.replace("mot20", "x").replace("mot40", "y"), 0.9),  # 4 : Jaccard 52/64
            (longue + " fin", 0.7),  # 5 : quasi-copie de 3 (Jaccard 58/59)
            ("Oui.", 1.0),  # 6
            ("Non.", 1.0),  # 7
            ("Oui.", 1.0),  # 8 : copie exacte, à égalité de confiance la première est gardée
        ]
    )
    assert dedoublonner(con, CFG.doublons) == 3
    groupes = dict(con.execute("SELECT prop_id, groupe_doublon FROM proposition"))
    assert groupes == {1: 2, 2: 2, 3: 3, 4: None, 5: 3, 6: 6, 7: None, 8: 6}
    aretes = con.execute("SELECT src, dst FROM arete WHERE type = 'DOUBLON_DE' ORDER BY 1")
    assert aretes.fetchall() == [(1, 2), (5, 3), (8, 6)]
    # Recalcul : même résultat, pas d'arête en double.
    assert dedoublonner(con, CFG.doublons) == 3
    assert con.execute("SELECT COUNT(*) FROM arete").fetchone()[0] == 3


def test_doublons_entre_fichiers(tmp_path):
    a = pdf_tableau(
        tmp_path / "A1.pdf", ["RAPPORT D'ENQUÊTE", "Le témoin arrive au poste."], [], []
    )
    b = pdf_tableau(
        tmp_path / "B1.pdf", ["RAPPORT DE SYNTHÈSE", "Le témoin arrive au poste."], [], []
    )
    con = ouvrir_stock(":memory:")
    ingerer_fichiers(con, [a, b], CFG)
    r = con.execute(
        "SELECT s.piece_id, d.piece_id FROM arete JOIN proposition s ON s.prop_id = src "
        "JOIN proposition d ON d.prop_id = dst WHERE type = 'DOUBLON_DE'"
    )
    assert r.fetchall() == [("B1", "A1")]
