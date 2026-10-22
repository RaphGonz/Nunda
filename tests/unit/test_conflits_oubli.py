"""Ingestion, étape 8 (conflits établis) et suppression d'une personne : test T8 (SPEC.md §5,
§14)."""

import json
import re

import pymupdf
import pytest
from typer.testing import CliRunner

from ccm.anonymize.names import nom_famille, norme
from ccm.cli import app
from ccm.config import load_config
from ccm.graph.store import ajouter_mentions, ajouter_nombres
from ccm.ingest.conflicts import detecter_conflits
from ccm.ingest.numbers import nombres
from ccm.ingest.racines import racines
from ccm.schema import ouvrir_stock
from ccm.search.bm25 import construire_index, dossier_index

CFG = load_config("ingest")
NOMS = {
    "Paul Morel": "PER",
    "MOREL Paul": "PER",
    "Jean Rival": "PER",
    "Hugo Non": "PER",
    "L.M.": "PER",
    "Lyon": "LIEU",
    "Brest": "LIEU",
}


def _mentions(texte, noms):
    """Mentions de chaque occurrence des noms (en attendant l'étape 5)."""
    return [
        (m.start(), m.end(), n, norme(n, CFG.noms), t, "regle")
        for n, t in noms.items()
        for m in re.finditer(re.escape(n), texte)
    ]


def _stock(lignes, noms=NOMS):
    """Une pièce par ligne (ou par (pièce, genre, texte)) ; mentions, nombres de l'étape 6."""
    con = ouvrir_stock(":memory:")
    ordre = {}
    for k, ligne in enumerate(lignes):
        piece, genre, texte = ligne if isinstance(ligne, tuple) else (f"P{k}", "PHRASE", ligne)
        if piece not in ordre:
            con.execute("INSERT INTO piece (piece_id) VALUES (?)", (piece,))
        ordre[piece] = ordre.get(piece, -1) + 1
        pid = con.execute(
            "INSERT INTO proposition (piece_id, ordre, texte, genre, ocr_conf) "
            "VALUES (?, ?, ?, ?, 1.0)",
            (piece, ordre[piece], texte, genre),
        ).lastrowid
        ms = _mentions(texte, noms)
        ajouter_mentions(con, pid, ms)
        ajouter_nombres(con, pid, nombres(texte, CFG.nombres, [(d, f) for d, f, *_ in ms]))
    return con


def conflits(con):
    detecter_conflits(con, CFG)
    q = "SELECT src, dst FROM arete WHERE type = 'CONFLIT' AND src < dst ORDER BY 1, 2"
    return con.execute(q).fetchall()


def test_nom_famille():
    attendu = {
        "MOREL Paul": "morel",
        "Paul Morel": "morel",
        "Mme Rot": "rot",
        "M. Boyer": "boyer",
        "Jean de la Fontaine": "de la fontaine",
        "DA SILVA Ana": "da silva",
        "Jean-Luc Borac": "borac",
        "L.M.": None,
        "J.-P.": None,
        "JP": None,
    }
    assert {s: nom_famille(s, CFG.noms) for s in attendu} == attendu


def test_norme():
    assert norme("M. Jean-Pierre DUPRÉ", CFG.noms) == "jean pierre dupre"
    assert norme("Maître  Éloïse   Vadec", CFG.noms) == "eloise vadec"
    assert norme("Major", CFG.noms) == "major"  # un mot seul reste


def test_meme_fait_heure_differente():
    con = _stock(
        [
            "Le 7 décembre 2024 à 21h59, Paul Morel a versé 1 250 € à la société Vadec.",
            "Le 07/12/2024 vers 23h10, MOREL Paul a fait un virement de 1250 euros à Vadec.",
            "Le 7 décembre 2024 à 21h59, Paul Morel a versé 1 250 € à la société Vadec.",
        ]
    )
    # 3 est une copie de 1 : seule la version gardée entre.
    con.execute("UPDATE proposition SET groupe_doublon = 1 WHERE prop_id IN (1, 3)")
    assert conflits(con) == [(1, 2)]
    # Arête dans les deux sens ; recalcul sans arête en double.
    assert con.execute("SELECT COUNT(*) FROM arete WHERE type = 'CONFLIT'").fetchone()[0] == 2
    assert conflits(con) == [(1, 2)]


def test_montants_en_recouvrement_partiel():
    con = _stock(
        [
            "Le 3 mai 2024, Paul Morel a versé 1 250 € et 300 € à Vadec.",
            "Le 3 mai 2024, Paul Morel a versé 1 250,00 € et 450 € à Vadec.",
            # Sous-ensemble de 1 ; sans montant commun avec 2 : un autre montant du fait.
            "Le 3 mai 2024, Paul Morel a versé 300 € à Vadec.",
        ]
    )
    assert conflits(con) == [(1, 2)]


@pytest.mark.parametrize(
    "a, b",
    [
        # Une date différente : un autre fait (répétition, ou alibi : conflit supposé).
        (
            "Le 8 mai 2024 à 10h00, Paul Morel a versé 100 €.",
            "Le 9 mai 2024 à 11h00, Paul Morel a versé 100 €.",
        ),
        # Aucun nom de famille commun ; des initiales n'en ont pas.
        (
            "Le 8 mai 2024 à 10h00, Paul Morel a versé 100 €.",
            "Le 8 mai 2024 à 15h00, Jean Rival a versé 100 €.",
        ),
        (
            "Le 8 mai 2024 à 10h00, Paul Morel a versé 100 €.",
            "Le 8 mai 2024 à 15h00, L.M. a versé 100 €.",
        ),
        # Deux actes différents le même jour.
        (
            "Le 8 mai 2024 à 10h00, Paul Morel a versé 100 €.",
            "Le 8 mai 2024 à 18h00, Paul Morel a été interpellé.",
        ),
        # Deux lieux différents.
        (
            "Le 8 mai 2024 à 10h00, à Lyon, Paul Morel a versé 100 €.",
            "Le 8 mai 2024 à 20h00, à Brest, Paul Morel a versé 100 €.",
        ),
        # Mêmes valeurs, écrites autrement (décimal exact).
        (
            "Le 8 mai 2024 à 10h00, Paul Morel a versé 1 250 € et 300 €.",
            "Le 08/05/2024 à 10:00, MOREL Paul a versé 1 250,00 € et 300,00 euros.",
        ),
        # Deux montants sans montant commun.
        ("Le 8 mai 2024, Paul Morel a versé 100 €.", "Le 8 mai 2024, Paul Morel a versé 250 €."),
        # « Non » dans un nom n'est pas une négation.
        (
            "Le 8 mai 2024, Hugo Non a signé le contrat.",
            "Le 8 mai 2024, Hugo Non a signé le contrat avec Vadec.",
        ),
    ],
)
def test_pas_de_conflit(a, b):
    assert conflits(_stock([a, b])) == []


def test_pas_de_conflit_dans_une_meme_piece():
    con = _stock(
        [
            ("P", "PHRASE", "Le 8 mai 2024 à 10h00, Paul Morel a versé 100 €."),
            ("P", "PHRASE", "Le 8 mai 2024 à 11h00, Paul Morel a versé 100 €."),
        ]
    )
    assert conflits(con) == []


def test_conflit_de_negation():
    con = _stock(
        [
            "Le 8 mai 2024, Paul Morel a signé le contrat de vente.",
            "Le 8 mai 2024, Paul Morel n'a pas signé le contrat de vente.",
        ]
    )
    assert conflits(con) == [(1, 2)]


def test_versions_d_un_article():
    con = _stock(
        [
            ("L1", "EN_TETE", "Code de commerce"),
            ("L1", "PHRASE", "Article L. 121-1"),
            ("L1", "PHRASE", "Le contrat est conclu par écrit."),  # 3
            ("L1", "PHRASE", "Il est signé par les parties."),
            ("L1", "PHRASE", "Article L. 121-2"),
            ("L1", "PHRASE", "Le délai est de trois mois."),
            ("L2", "EN_TETE", "Code de commerce"),
            ("L2", "PHRASE", "Art. L121-1"),  # autre graphie de la même référence
            ("L2", "PHRASE", "Le contrat est conclu par écrit ou par voie électronique."),  # 9
            ("L2", "PHRASE", "Il est signé par les parties."),
            ("L2", "PHRASE", "Article L. 121-2"),
            ("L2", "PHRASE", "Le délai est de trois mois."),
            # Même numéro, autre code : pas le même article.
            ("L3", "PHRASE", "Article L. 121-1 du Code civil"),
            ("L3", "PHRASE", "Le contrat est oral."),
            # Sans code lu : ne se compare qu'à un article sans code.
            ("L4", "PHRASE", "Article L. 121-1"),
            ("L4", "PHRASE", "Le contrat est tacite."),
        ],
        noms={},
    )
    assert conflits(con) == [(3, 9)]


def _pdf(chemin, lignes):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for k, s in enumerate(lignes):
        page.insert_text((56, 70 + 20 * k), s, fontsize=10.5)
    doc.save(chemin)


NOMS_T8 = ["Talmo Brévaneau", "BRÉVANEAU Talmo", "Brévaneau"]
CHAINES = ["Brévaneau", "BRÉVANEAU", "brevaneau", "Brevaneau", "Talmo", "talmo"]


def test_t8_oubli(tmp_path):
    """T8 : après `ccm forget`, la chaîne est absente de l'index, de la base et du fichier
    brut de la base."""
    src = tmp_path / "src"
    src.mkdir()
    _pdf(
        src / "A1.pdf",
        [
            "PROCÈS-VERBAL D'AUDITION",
            "Le 7 décembre 2024 à 21h59, Talmo Brévaneau a versé 1 250 euros à Paul Morel.",
            "Nous entendons BRÉVANEAU Talmo, né le 3 mai 1980.",
            "Paul Morel confirme le versement.",
        ],
    )
    _pdf(
        src / "A2.pdf",
        [
            "PROCÈS-VERBAL D'AUDITION",
            "Le 7 décembre 2024 à 23h10, Talmo Brévaneau a versé 1 250 euros à Paul Morel.",
            "Brévaneau déclare ne rien savoir.",
        ],
    )
    stock = tmp_path / "stock.sqlite"
    r = CliRunner().invoke(app, ["ingest", str(src), "--stock", str(stock)])
    assert r.exit_code == 0, r.output

    # Mentions posées à la main à la place de celles de l'étape 5 (le test ne dépend pas
    # des détecteurs), puis index et conflits.
    con = ouvrir_stock(stock)
    con.execute("DELETE FROM mention")
    for pid, texte in con.execute("SELECT prop_id, texte FROM proposition").fetchall():
        ajouter_mentions(con, pid, _mentions(texte, {n: "PER" for n in NOMS_T8 + ["Paul Morel"]}))
    con.execute(
        "INSERT INTO contrainte VALUES ('c1', 'MEME', ?, ?, NULL, 'u', '2026-10-21')",
        (norme(NOMS_T8[0], CFG.noms), norme(NOMS_T8[2], CFG.noms)),
    )
    con.execute(
        "INSERT INTO trace (reponse_id, question, revision_base) VALUES "
        "('r1', 'Combien a versé Brévaneau ?', 2)"
    )
    detecter_conflits(con, CFG)
    con.commit()
    avant = dict(con.execute("SELECT piece_id, revision FROM piece"))
    assert con.execute("SELECT COUNT(*) FROM arete WHERE type = 'CONFLIT'").fetchone()[0] == 2
    index = dossier_index(stock)
    construire_index(con, index, CFG, load_config("search"))
    con.close()
    assert "brevaneau" in "".join(p.read_text("utf-8", "replace") for p in index.iterdir())

    normes = sorted({norme(n, CFG.noms) for n in NOMS_T8})
    r = CliRunner().invoke(app, ["forget", *normes, "--stock", str(stock)])
    assert r.exit_code == 0, r.output

    # Base : aucune colonne texte d'aucune table ne contient la chaîne.
    con = ouvrir_stock(stock)
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        for ligne in con.execute(f"SELECT * FROM {table}").fetchall():
            for v in ligne:
                if isinstance(v, str):
                    assert not any(c.casefold() in v.casefold() for c in CHAINES), (table, v)
    # Le reste est intact : Paul Morel, les nombres, les positions.
    textes = [t for (t,) in con.execute("SELECT texte FROM proposition ORDER BY prop_id")]
    assert (
        textes[1] == "Le 7 décembre 2024 à 21h59, ███████████████ a versé 1 250 euros à Paul Morel."
    )
    assert textes[-1] == "█████████ déclare ne rien savoir."
    assert con.execute("SELECT DISTINCT norme FROM mention").fetchall() == [("paul morel",)]
    assert con.execute("SELECT COUNT(*) FROM contrainte").fetchone()[0] == 0
    apres = dict(con.execute("SELECT piece_id, revision FROM piece"))
    assert all(apres[p] > max(avant.values()) for p in ("A1", "A2"))
    con.close()

    # Fichier brut de la base (et pas de journal laissé à côté).
    brut = stock.read_bytes()
    for c in CHAINES:
        for forme in {c, c.upper(), c.lower()}:
            assert forme.encode("utf-8") not in brut
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "src",
        "stock.sqlite",
        "stock.sqlite.bm25",
    ]

    # Index BM25 : ni la chaîne, ni sa racine ; les prop_id des versions gardées.
    racine = racines("Brévaneau Talmo", CFG.racines)
    for p in index.iterdir():
        contenu = p.read_bytes().decode("utf-8", "replace").casefold()
        for c in CHAINES + racine:
            assert c.casefold() not in contenu, (p.name, c)
    con = ouvrir_stock(stock)
    q = "SELECT prop_id FROM proposition WHERE groupe_doublon IS NULL OR groupe_doublon = prop_id"
    ids = [p for (p,) in con.execute(q + " ORDER BY prop_id")]
    assert len(ids) == len(textes) - 1  # l'en-tête de A2, doublon non gardé, est hors index
    assert json.loads((index / "prop_ids.json").read_text("utf-8")) == ids
