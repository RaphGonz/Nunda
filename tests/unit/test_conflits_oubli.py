"""Ingestion, étape 8 (conflits) et suppression d'une personne : test T8 (SPEC.md §5, §14)."""

import json
import re

import pymupdf
from typer.testing import CliRunner

from ccm.anonymize.names import norme
from ccm.cli import app
from ccm.config import load_config
from ccm.graph.store import ajouter_mentions, ajouter_nombres
from ccm.ingest.conflicts import detecter_conflits, signature
from ccm.ingest.numbers import nombres
from ccm.ingest.racines import racines
from ccm.schema import ouvrir_stock
from ccm.search.bm25 import construire_index, dossier_index

CFG = load_config("ingest")


def _mentions(texte, noms):
    """Mentions PER de chaque occurrence des noms (en attendant l'étape 5)."""
    return [
        (m.start(), m.end(), n, norme(n, CFG.noms), "PER", "regle")
        for n in noms
        for m in re.finditer(re.escape(n), texte)
    ]


def _stock(lignes, noms=()):
    """Une pièce par ligne ; mentions des `noms`, nombres de l'étape 6."""
    con = ouvrir_stock(":memory:")
    for k, texte in enumerate(lignes):
        con.execute("INSERT INTO piece (piece_id) VALUES (?)", (f"P{k}",))
        pid = con.execute(
            "INSERT INTO proposition (piece_id, ordre, texte, ocr_conf) VALUES (?, 0, ?, 1.0)",
            (f"P{k}", texte),
        ).lastrowid
        ms = _mentions(texte, noms)
        ajouter_mentions(con, pid, ms)
        ajouter_nombres(con, pid, nombres(texte, CFG.nombres, [(d, f) for d, f, *_ in ms]))
    return con


def conflits(con):
    detecter_conflits(con, CFG)
    q = "SELECT src, dst FROM arete WHERE type = 'CONFLIT' AND src < dst ORDER BY 1, 2"
    return con.execute(q).fetchall()


def test_signature():
    texte = "Le 7 décembre 2024 à 21h59, Paul Morel a versé 1 250 € à la société."
    ms = [(t[0], t[1], "PER") for t in _mentions(texte, ["Paul Morel"])]
    ns = [(n.debut, n.fin, n.genre, n.unite) for n in nombres(texte, CFG.nombres)]
    assert signature(texte, ms, ns, CFG) == {
        "DATE",
        "NUM:heure_du_jour",
        "NUM:€",
        "PER",
        *racines("a versé société", CFG.racines),
    }


def test_conflit_de_valeur():
    con = _stock(
        [
            "Le 7 décembre 2024 à 21h59, Paul Morel a versé 1 250 € à la société Vadec.",
            "Le 7 décembre 2024 à 23h10, Paul Morel a versé 1 250 € à la société Vadec.",
            "Le 7 décembre 2024 à 21h59, Paul Morel a versé 1 250 € à la société Vadec.",
            "Le 7 décembre 2024 à 21h59, Paul Morel a versé 900 € à la société Vadec.",
        ],
        ["Paul Morel"],
    )
    # 1 et 3 sont des copies : 3 n'est pas une version gardée.
    con.execute("UPDATE proposition SET groupe_doublon = 1 WHERE prop_id IN (1, 3)")
    assert conflits(con) == [(1, 2), (1, 4), (2, 4)]
    # Arête dans les deux sens.
    assert con.execute("SELECT COUNT(*) FROM arete WHERE type = 'CONFLIT'").fetchone()[0] == 6
    # Recalcul : pas d'arête en double.
    assert conflits(con) == [(1, 2), (1, 4), (2, 4)]


def test_pas_de_conflit():
    con = _stock(
        [
            # Mêmes valeurs ; une date moins précise n'est pas une autre date.
            "En décembre 2024, Paul Morel a versé 1 250 € à la société Vadec.",
            "Le 7 décembre 2024, Paul Morel a versé 1 250 € à la société Vadec.",
            # Noms non inclus l'un dans l'autre.
            "Le 7 décembre 2024, Jean Rival a versé 300 € à la société Vadec.",
            # Texte trop différent (Jaccard < 0,6).
            "Le 9 mars 2023, Paul Morel a reçu 300 € pour la vente de la voiture rouge.",
        ],
        ["Paul Morel", "Jean Rival"],
    )
    assert conflits(con) == []


def test_conflit_de_negation():
    con = _stock(
        [
            "Paul Morel a signé le contrat de vente avec la société Vadec.",
            "Paul Morel n'a pas signé le contrat de vente avec la société Vadec.",
            "Paul Morel a signé le contrat de vente avec la société Vadec hier.",
        ],
        ["Paul Morel"],
    )
    assert conflits(con) == [(1, 2), (2, 3)]


def test_norme():
    assert norme("M. Jean-Pierre DUPRÉ", CFG.noms) == "jean pierre dupre"
    assert norme("Maître  Éloïse   Vadec", CFG.noms) == "eloise vadec"
    assert norme("Major", CFG.noms) == "major"  # un mot seul reste


def _pdf(chemin, lignes):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for k, s in enumerate(lignes):
        page.insert_text((56, 70 + 20 * k), s, fontsize=10.5)
    doc.save(chemin)


NOMS = ["Talmo Brévaneau", "BRÉVANEAU Talmo", "Brévaneau"]
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

    # Étape 5 (pas encore écrite) : mentions posées à la main, puis index et conflits.
    con = ouvrir_stock(stock)
    for pid, texte in con.execute("SELECT prop_id, texte FROM proposition").fetchall():
        ajouter_mentions(con, pid, _mentions(texte, NOMS + ["Paul Morel"]))
    con.execute(
        "INSERT INTO contrainte VALUES ('c1', 'MEME', ?, ?, NULL, 'u', '2026-10-21')",
        (norme(NOMS[0], CFG.noms), norme(NOMS[2], CFG.noms)),
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

    normes = sorted({norme(n, CFG.noms) for n in NOMS})
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
