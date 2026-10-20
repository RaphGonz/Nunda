"""Ingestion, étapes 1 à 3 bis (SPEC.md §5) : extraction, pièces et types, segmentation."""

from collections import Counter

import pymupdf
import pytest
from typer.testing import CliRunner

from ccm.cli import app
from ccm.config import load_config
from ccm.data.worldgen.corpus import produire_dossier
from ccm.ingest.extract import tesseract
from ccm.ingest.pipeline import ingerer_fichier
from ccm.ingest.segment import phrases
from ccm.schema import ouvrir_stock

CFG = load_config("ingest")
WORLDGEN = load_config("worldgen")
MARGE, PAS, ESPACE, TAILLE = 56, 14, 6, 10.5


def ecrire_pdf(chemin, pages, colonnes=1):
    """Chaque page : liste de paragraphes ; chaque paragraphe : liste de lignes. Avec deux
    colonnes, les paragraphes se répartissent moitié à gauche, moitié à droite."""
    doc = pymupdf.open()
    for paragraphes in pages:
        page = doc.new_page(width=595, height=842)
        moitie = (len(paragraphes) + 1) // 2 if colonnes == 2 else len(paragraphes)
        for c, groupe in enumerate([paragraphes[:moitie], paragraphes[moitie:]]):
            y = MARGE
            for lignes in groupe:
                for s in lignes:
                    page.insert_text((MARGE + c * 280, y + PAS - 3), s, fontsize=TAILLE)
                    y += PAS
                y += ESPACE
    doc.save(chemin)
    return chemin


def ingerer(chemin):
    con = ouvrir_stock(":memory:")
    ingerer_fichier(con, chemin, CFG)
    return con


def textes(con, piece=None):
    q = "SELECT texte FROM proposition" + (" WHERE piece_id = ?" if piece else "")
    return [r[0] for r in con.execute(q + " ORDER BY prop_id", (piece,) if piece else ())]


def aretes(con, type_):
    q = (
        "SELECT a.ordre, b.ordre FROM arete JOIN proposition a ON a.prop_id = src "
        "JOIN proposition b ON b.prop_id = dst WHERE type = ? ORDER BY 1, 2"
    )
    return con.execute(q, (type_,)).fetchall()


def test_phrases_abreviations_et_initiales():
    c = CFG.segmentation
    t = "Me Martin cite l'art. L. 121-1 du Code. Le 3 févr. 2024, É.M. et M. Dupont partent."
    assert [t[a:b] for a, b in phrases(t, c)] == [
        "Me Martin cite l'art. L. 121-1 du Code.",
        "Le 3 févr. 2024, É.M. et M. Dupont partent.",
    ]
    t = "Le P.V. n° 12 est clos. Signatures : É.L."
    assert [t[a:b] for a, b in phrases(t, c)] == ["Le P.V. n° 12 est clos.", "Signatures : É.L."]


def test_depend_de_et_suivante(tmp_path):
    pages = [
        [
            ["RAPPORT D'ENQUÊTE"],
            ["Le témoin arrive au poste de police. Il déclare avoir vu la voiture."],
            ["Oui, exact."],
            ["Le véhicule était rouge et garé devant la gare."],
            ["Toutefois, personne ne l'a vu partir ce soir-là."],
            ["Ilona Martin confirme ces déclarations devant nous."],
        ]
    ]
    con = ingerer(ecrire_pdf(tmp_path / "R1.pdf", pages))
    assert textes(con)[:3] == [
        "RAPPORT D'ENQUÊTE",
        "Le témoin arrive au poste de police.",
        "Il déclare avoir vu la voiture.",
    ]
    genres = [r[0] for r in con.execute("SELECT genre FROM proposition ORDER BY ordre")]
    assert genres == ["EN_TETE"] + ["PHRASE"] * 6
    assert aretes(con, "DEPEND_DE") == [(2, 1), (3, 2), (5, 4)]
    assert aretes(con, "SUIVANTE") == [(k, k + 1) for k in range(6)]
    assert con.execute("SELECT type, rang, nb_pages FROM piece").fetchone() == ("RAPPORT", 0, 1)


def test_question_reponse_d_audition(tmp_path):
    pages = [
        [
            ["PROCÈS-VERBAL D'AUDITION"],
            ["Question : Où étiez-vous le soir des faits ?"],
            ["Réponse : J'étais chez moi avec ma sœur toute la soirée."],
            ["Question : Connaissez-vous le gérant du garage du centre ?"],
            ["Je le connais depuis l'école, nous sommes restés amis."],
        ]
    ]
    con = ingerer(ecrire_pdf(tmp_path / "A1.pdf", pages))
    assert con.execute("SELECT type FROM piece").fetchone() == ("PV_AUDITION",)
    assert aretes(con, "DEPEND_DE") == [(2, 1), (4, 3)]
    # Hors audition, la même suite ne crée pas de dépendance.
    pages[0][0] = ["RAPPORT D'ENQUÊTE"]
    assert aretes(ingerer(ecrire_pdf(tmp_path / "R2.pdf", pages)), "DEPEND_DE") == []


def test_phrase_longue_coupee_en_parties(tmp_path):
    mots = ["le témoin a vu une voiture rouge devant la gare"] * 3
    phrase = "Premièrement " + " ".join(mots) + " ; ensuite " + " ".join(mots) + " : enfin "
    phrase += " ".join(mots) + "."
    assert len(phrase.split()) > CFG.segmentation.mots_max
    lignes, courante = [], ""
    for m in phrase.split(" "):  # coupure aux espaces, comme le générateur
        if len(courante) + len(m) > 80:
            lignes.append(courante)
            courante = m
        else:
            courante = f"{courante} {m}" if courante else m
    con = ingerer(ecrire_pdf(tmp_path / "L1.pdf", [[["RAPPORT D'ENQUÊTE"], lignes + [courante]]]))
    parties = textes(con)[1:]
    assert len(parties) == 3 and " ".join(parties) == phrase
    assert parties[0].endswith(";") and parties[1].endswith(":")
    genres = {r[0] for r in con.execute("SELECT genre FROM proposition WHERE ordre > 0")}
    assert genres == {"PARTIE"}
    assert aretes(con, "DEPEND_DE") == [(1, 2), (2, 1), (2, 3), (3, 2)]


def test_mots_coupes_en_fin_de_ligne(tmp_path):
    pages = [[["RAPPORT D'ENQUÊTE"], ["Le témoi-", "gnage de la SAS Import-", "Export est clos."]]]
    con = ingerer(ecrire_pdf(tmp_path / "C1.pdf", pages))
    assert textes(con)[1] == "Le témoignage de la SAS Import-Export est clos."


def test_deux_colonnes(tmp_path):
    phrases = [
        f"{c} {k} : le témoin arrive au poste de police."
        for c in ("Gauche", "Droite")
        for k in ("un", "deux")
    ]
    con = ingerer(ecrire_pdf(tmp_path / "K1.pdf", [[[p] for p in phrases]], colonnes=2))
    assert textes(con) == phrases


def test_paragraphe_sur_deux_pages(tmp_path):
    debut = "Le témoin déclare que la voiture rouge stationnait devant la gare depuis le"
    fin = "matin, sans conducteur."
    plein = [[f"Ligne de remplissage numéro {k}."] for k in range(36)]
    con = ingerer(ecrire_pdf(tmp_path / "S1.pdf", [plein + [[debut]], [[fin], ["Fin."]]]))
    rows = con.execute("SELECT page, texte FROM proposition ORDER BY ordre").fetchall()
    assert rows[-2:] == [(1, f"{debut} {fin}"), (2, "Fin.")]
    # Une ligne courte en bas de page ne continue pas.
    con = ingerer(ecrire_pdf(tmp_path / "S2.pdf", [plein + [["Court :"]], [[fin]]]))
    assert textes(con)[-2:] == ["Court :", fin]


def test_plusieurs_pieces_dans_un_fichier(tmp_path):
    pages = [
        [["RAPPORT D'ENQUÊTE"], ["Le rapport commence ici."]],
        [["PROCÈS-VERBAL D'AUDITION"], ["Le témoin parle ici."]],
        [["La suite de l'audition continue sur cette page."]],
    ]
    chemin = ecrire_pdf(tmp_path / "F1.pdf", pages)
    con = ingerer(chemin)
    pieces = con.execute("SELECT piece_id, type, nb_pages, revision FROM piece").fetchall()
    assert pieces == [("F1", "RAPPORT", 1, 1), ("F1.2", "PV_AUDITION", 2, 2)]
    assert textes(con, "F1.2")[-1] == "La suite de l'audition continue sur cette page."
    assert con.execute("SELECT page FROM proposition WHERE piece_id = 'F1.2'").fetchall() == [
        (2,),
        (2,),
        (3,),
    ]
    assert ingerer_fichier(con, chemin, CFG) == []  # même SHA-256 : ignoré


@pytest.mark.skipif(tesseract(CFG.extraction) is None, reason="Tesseract absent")
def test_ocr_d_une_page_image(tmp_path):
    src = pymupdf.open(
        ecrire_pdf(
            tmp_path / "N1.pdf", [[["RAPPORT D'ENQUÊTE"], ["Le témoin arrive au poste de police."]]]
        )
    )
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=src[0].get_pixmap(dpi=200))
    doc.save(tmp_path / "O1.pdf")
    con = ingerer(tmp_path / "O1.pdf")
    rows = con.execute("SELECT texte, ocr_conf FROM proposition ORDER BY ordre").fetchall()
    assert [t for t, _ in rows] == ["RAPPORT D'ENQUÊTE", "Le témoin arrive au poste de police."]
    assert all(0 < c < 1 for _, c in rows)


def test_dossier_synthetique(tmp_path):
    """Chaque ligne d'une pièce synthétique est une proposition ; un champ, une ligne de
    tableau, un en-tête (sauf de courrier) en gardent le genre ; chaque nombre, date et
    heure déclaré est lu."""
    for graine in (1_000_000, 1_000_003):
        d, pdfs, erreurs = produire_dossier(graine, "entrainement", WORLDGEN, frozenset())
        assert not erreurs
        con = ouvrir_stock(":memory:")
        for piece in d.pieces:
            chemin = tmp_path / f"{d.id}-{piece.id}.pdf"
            chemin.write_bytes(pdfs[piece.id])
            assert len(ingerer_fichier(con, chemin, CFG)) == 1
            props = Counter(
                con.execute(
                    "SELECT texte, genre FROM proposition WHERE piece_id = ?", (chemin.stem,)
                )
            )
            attendues = Counter(
                (x.texte, x.genre)
                for x in piece.lignes
                if x.genre != "PHRASE" and not (x.genre == "EN_TETE" and piece.type == "COURRIER")
            )
            assert attendues - props == Counter(), piece.id
            assert (
                Counter(x.texte for x in piece.lignes) - Counter(t for t, _ in props) == Counter()
            )
            lus = Counter(
                r[0]
                for r in con.execute(
                    "SELECT surface FROM nombre JOIN proposition USING (prop_id) "
                    "WHERE piece_id = ?",
                    (chemin.stem,),
                )
            )
            declares = Counter(
                f.surface
                for x in piece.lignes
                for f in x.faits
                if f.genre in ("NUM", "DATE", "HEURE")
            )
            assert declares - lus == Counter(), piece.id
            t = con.execute("SELECT type FROM piece WHERE piece_id = ?", (chemin.stem,)).fetchone()
            assert t[0] == ("AUTRE" if piece.type == "COURRIER" else piece.type)


def test_commande_ingest(tmp_path):
    ecrire_pdf(tmp_path / "R1.pdf", [[["RAPPORT D'ENQUÊTE"], ["Le témoin arrive."]]])
    stock = tmp_path / "stock.sqlite"
    r = CliRunner().invoke(app, ["ingest", str(tmp_path), "--stock", str(stock)])
    assert r.exit_code == 0, r.output
    assert "1 pièces ajoutées ; 2 propositions" in r.output
    r = CliRunner().invoke(app, ["ingest", str(tmp_path / "R1.pdf"), "--stock", str(stock)])
    assert "0 pièces ajoutées ; 2 propositions" in r.output
