"""Vérificateur (SPEC.md §11, étapes 1 à 9) : petit stock écrit à la main, et suites de
référence du corpus synthétique."""

import json
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from ccm.anonymize.exemple import Message, anonymiser
from ccm.anonymize.names import norme
from ccm.anonymize.table import TableConversation
from ccm.config import load_config
from ccm.data.worldgen.cibles import cible_de_reference, exemple_de_reference
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pieces import rediger_dossier
from ccm.data.worldgen.questions import poser_questions
from ccm.eval.equivariance import message_de_reference, stock_de_reference
from ccm.grammar.units import DATE, DUREE, POURCENT, SANS_UNITE, Valeur
from ccm.graph.store import ajouter_mentions, ajouter_nombres, ajouter_piece
from ccm.ingest.numbers import nombres
from ccm.schema import GenreProposition, TypeArete, TypeNom, TypePiece, ouvrir_stock
from ccm.verify import render as R
from ccm.verify.verifier import Entree, appliquer_exact, exact, verifier

CFG = load_config("ingest")
GCFG = load_config("grammar")
VCFG = load_config("verify")
WCFG = load_config("worldgen")
PER = TypeNom.PER


# --- Calcul exact (étape 3) --------------------------------------------------------------


def _v(unite, x, precision=None):
    return exact(Valeur(unite, Decimal(x) if unite != DATE else x, precision))


@pytest.mark.parametrize(
    "op, a, b, attendu",
    [
        ("+", _v("€", "0.1"), _v("€", "0.2"), "0,3 €"),
        ("+", _v("€", "1200"), _v("€", "300"), "1 500 €"),
        ("−", _v("€", "300"), _v("€", "1200"), "−900 €"),
        ("÷", _v("€", "1"), _v("€", "3"), "≈ 0,33"),
        ("÷", _v("€", "1"), _v("€", "8"), "0,125"),
        ("×", _v("€", "1500"), _v(POURCENT, "0.2"), "300 €"),
        ("÷", _v("€", "300"), _v("€", "1500"), "0,2"),
        ("MAX", _v("km", "12.5"), _v("km", "3"), "12,5 km"),
        ("−", _v(DATE, date(2024, 3, 12), "JOUR"), _v(DATE, date(2024, 3, 1), "JOUR"), "11 jours"),
        ("+", _v(DATE, date(2024, 2, 28), "JOUR"), _v(DUREE, "2"), "01/03/2024"),
        ("MIN", _v("heure du jour", "1319"), _v("heure du jour", "600"), "10 h 00"),
        ("+", _v("jour", "0.5"), _v("jour", "0.5"), "1 jour"),
    ],
)
def test_calcul_exact(op, a, b, attendu):
    r = appliquer_exact(op, a, b)
    assert R.ecrire_valeur(r.unite, r.valeur, r.precision, VCFG.decimales) == attendu


def test_calcul_exact_refus():
    assert appliquer_exact("÷", _v("€", "1"), _v("€", "0")) is None
    assert appliquer_exact("+", _v("€", "1"), _v("km", "1")) is None
    assert appliquer_exact("+", _v(DATE, date(2024, 1, 1), "JOUR"), _v(DUREE, "0.5")) is None
    # Décimal exact : aucune perte, même au-delà de 28 chiffres.
    r = appliquer_exact("+", _v("€", "1e30"), _v("€", "0.000001"))
    assert r.valeur == Fraction(10**30) + Fraction(1, 10**6)
    assert R.ecrire_nombre(Fraction(-1234567), 2) == "−1 234 567"
    assert R.ecrire_valeur(SANS_UNITE, Fraction(2, 3), None, 2) == "≈ 0,67"


# --- Petit stock -----------------------------------------------------------------------
# Pièce A (rang 1) : a0 ; a1 dépend de a0. Pièce B (rang 3) : b0 à b5 ; b3 est en conflit
# avec a1. Pièce C : c0 en conflit avec a1 ; ignorée dans la conversation « c1 ».
# Contexte : a1, b0, b1, b2, b4, b5 (ni a0, ni b3, ni c0).

NOMS = ("Jean Martin", "J. Martin", "Paul Durand", "Lyon")
TEXTES = {
    "A": ["Jean Martin a signé le contrat le 12 mars 2024.", "Il a payé 1 200 euros."],
    "B": [
        "J. Martin a payé 1 500 euros le 12 mars 2024.",
        "Paul Durand habite à Lyon.",
        "Le contrat doit être signé par écrit.",
        "Il a payé 900 euros.",
        "Le contrat est rédigé en deux exemplaires.",
        "La réunion a eu lieu le matin.",
    ],
    "C": ["Il a payé 950 euros."],
}


def _mentions(texte):
    out = []
    for s in NOMS:
        d = texte.find(s)
        if d >= 0 and not any(d >= a and d < b for a, b, *_ in out):
            t = TypeNom.LIEU if s == "Lyon" else PER
            out.append((d, d + len(s), s, norme(s, CFG.noms), str(t), "reference"))
    return out


def _message(texte):
    zs = _mentions(texte)
    return Message(texte, tuple((d, f, TypeNom(t)) for d, f, _, _, t, _ in zs),
                   tuple(nombres(texte, CFG.nombres, [(d, f) for d, f, *_ in zs])))  # fmt: skip


@pytest.fixture
def stock():
    con = ouvrir_stock(":memory:")
    ids = {}
    for piece, rang in (("A", 1), ("B", 3), ("C", 1)):
        props = [(1, t, GenreProposition.PHRASE, 0.5 if t.startswith("Le contrat doit") else 1.0)
                 for t in TEXTES[piece]]  # fmt: skip
        aretes = [(1, 0, TypeArete.DEPEND_DE)] if piece == "A" else []
        pids = ajouter_piece(con, piece, f"{piece}.pdf", piece, TypePiece.PV_AUDITION, rang, 1,
                             props, aretes)  # fmt: skip
        for k, (pid, t) in enumerate(zip(pids, TEXTES[piece], strict=True)):
            ids[f"{piece.lower()}{k}"] = pid
            zs = _mentions(t)
            ajouter_mentions(con, pid, zs)
            ajouter_nombres(con, pid, nombres(t, CFG.nombres, [(d, f) for d, f, *_ in zs]))
    for x, y in (("a1", "b3"), ("a1", "c0")):
        con.executemany("INSERT INTO arete VALUES (?, ?, 'CONFLIT')",
                        [(ids[x], ids[y]), (ids[y], ids[x])])  # fmt: skip
    con.execute("INSERT INTO contrainte (conv_id, genre, piece_id) VALUES ('c1', "
                "'IGNORER_SOURCE', 'C')")  # fmt: skip
    yield con, ids
    con.close()


CONTEXTE = ["a1", "b0", "b1", "b2", "b4", "b5"]


def _entree(con, ids, question, conv_id="c1", probabilites=None):
    q, t = _message(question), TableConversation(0, CFG.anonymiseur.reservoir)
    ex = anonymiser(con, [ids[x] for x in CONTEXTE], q, t, CFG, conv_id=conv_id)
    return Entree(ex, t.valeurs(), q, probabilites=probabilites or {}, conv_id=conv_id)


def _n(entree, local, unite="€"):
    p = entree.ex.propositions[local]
    j = next(j for j, m in enumerate(p.marques) if m.genre == "NUM" and m.unite == unite)
    return f"N:{local}.{j}"


def _m(entree, t, j=0):
    return f"M:{t}.{j}"


def _verifier(con, entree, suite, **kw):
    return verifier(con, entree, suite, CFG, GCFG, VCFG, **kw)


def test_etapes_2_a_7_et_9(stock):
    con, ids = stock
    e = _entree(con, ids, "Combien Jean Martin a-t-il payé ?", probabilites={4: 0.9, 5: 0.1})
    suite = ["P:0", "ET", "P:1", "ET", "P:2", "ET", "P:3", "DONC", "CALCUL", _n(e, 0), _n(e, 1),
             "+", "FIN_CALCUL", "FIN"]  # fmt: skip
    rep = _verifier(con, e, suite, modele="oracle")
    assert rep.erreur is None, rep.erreur
    styles = [b.style for b in rep.blocs]
    textes = [b.texte for b in rep.blocs]
    # Étape 2 : a0, hors du contexte, affiché avant a1, style « contexte ».
    assert textes[0] == "Contexte : " + TEXTES["A"][0] + " (pièce A, page 1)"
    assert textes[1] == "[1] Il a payé 1 200 euros. (pièce A, page 1)"
    # Étape 4 : b3 (hors du contexte) affiché ; c0 (pièce ignorée) exclu ; rangs 1 et 3.
    i = textes.index(R.CONFLIT)
    assert textes[i + 1].startswith("[1] Il a payé 1 200 euros.")
    assert textes[i + 2].startswith("[2] Il a payé 900 euros. (pièce B, page 1)")
    assert textes[i + 3] == "Rang : pièce A : 1, pièce B : 3."
    assert "950" not in rep.texte
    # Étape 5 : ancrage.
    assert "Lien non confirmé : « J. Martin » (cette citation) et « Jean Martin ». Ressemblance" \
        in rep.texte  # fmt: skip
    assert textes.count(R.AUCUN_NOM) == 1  # b1 ; ni a1 ni b2 (aucun nom)
    assert textes[textes.index(R.AUCUN_NOM) - 1].startswith("[4] Paul Durand")
    # Étape 7 : OCR bas.
    assert "[5] Le contrat doit être signé par écrit. (pièce B, à vérifier sur la page 1)" in textes
    # Étape 3 : opérandes reliés à leur citation, résultat exact.
    assert "donc (inférence du modèle)" in textes
    assert "Calcul : 1 200 euros [1] + 1 500 euros [3] = 2 700 €" in textes
    # Étape 6 : b4 (0,9 ≥ seuil) ; pas b5 (0,1).
    j = styles.index("autres")
    assert textes[j] == R.AUTRES
    assert textes[j + 1].startswith("[6] Le contrat est rédigé en deux exemplaires.")
    assert "réunion" not in rep.texte
    # Étape 9 : trace.
    actions, modele = con.execute(
        "SELECT actions, modele FROM trace WHERE reponse_id = ?", (rep.reponse_id,)
    ).fetchone()
    assert modele == "oracle"
    assert json.loads(actions)["citees"] == [ids[x] for x in CONTEXTE[:4]]


def test_conflit_de_piece_ignoree_visible_sans_contrainte(stock):
    con, ids = stock
    e = _entree(con, ids, "Combien Jean Martin a-t-il payé ?", conv_id="autre")
    rep = _verifier(con, e, ["P:0", "FIN"])
    assert "Il a payé 950 euros." in rep.texte and "Il a payé 900 euros." in rep.texte


def test_conflit_deja_affiche_pas_de_bloc_ajoute(stock):
    con, ids = stock
    e = _entree(con, ids, "Combien Jean Martin a-t-il payé ?")
    rep = _verifier(con, e, ["CONFLIT", "SANS_PREUVE", "P:0", "P:1", "FIN_CONFLIT", "FIN"])
    textes = [b.texte for b in rep.blocs]
    assert textes[1] == R.CONFLIT_SANS_PREUVE
    assert textes.count(R.CONFLIT) == 1  # b3, conflit établi de a1, hors du contexte


def test_ancrage_same_et_contrainte(stock):
    con, ids = stock
    e = _entree(con, ids, "Combien Jean Martin a-t-il payé ?")
    rep = _verifier(con, e, ["SAME", _m(e, "q"), _m(e, 1), "SANS_PREUVE", "ET", "P:1", "FIN"])
    assert rep.erreur is None, rep.erreur
    assert rep.blocs[0].texte == (
        "Hypothèse fondée sur la seule ressemblance des noms : « Jean Martin » et « J. Martin »."
    )
    assert "Lien non confirmé" not in rep.texte
    con.execute("INSERT INTO contrainte (conv_id, genre, a_norme, b_norme) VALUES "
                "('c2', 'MEME', ?, ?)", (norme("Jean Martin", CFG.noms),
                                         norme("J. Martin", CFG.noms)))  # fmt: skip
    e = _entree(con, ids, "Combien Jean Martin a-t-il payé ?", conv_id="c2")
    rep = _verifier(con, e, ["P:1", "FIN"])
    assert "Lien non confirmé" not in rep.texte and R.AUCUN_NOM not in rep.texte


def test_ancrage_sans_nom_dans_la_question(stock):
    con, ids = stock
    e = _entree(con, ids, "Qui habite à quel endroit ?")
    rep = _verifier(con, e, ["P:2", "FIN"])
    assert "Lien non confirmé" not in rep.texte and R.AUCUN_NOM not in rep.texte


def test_note_same_enregistree_et_relance_une_fois(stock):
    con, ids = stock
    q = "Jean Martin et J. Martin sont la même personne."
    e = _entree(con, ids, q)
    appels = []

    def relancer():
        appels.append(1)
        return _verifier(con, _entree(con, ids, q), ["P:1", "FIN"])

    rep = _verifier(con, e, ["NOTE_SAME", _m(e, "q", 0), _m(e, "q", 1), "FIN"], relancer=relancer)
    assert appels == [1]
    assert rep.blocs[0].texte == (
        "Noté : « Jean Martin » et « J. Martin » sont la même personne (votre déclaration)."
    )
    assert [c[0] for c in rep.contraintes] == ["MEME"]
    assert con.execute("SELECT a_norme, b_norme FROM contrainte WHERE conv_id = 'c1' AND genre = "
                       "'MEME'").fetchone() == (norme("Jean Martin", CFG.noms),
                                                norme("J. Martin", CFG.noms))  # fmt: skip
    # La relance voit la contrainte : J. Martin est lié par un lien sûr.
    assert "Lien non confirmé" not in rep.texte


def test_suite_refusee(stock):
    con, ids = stock
    e = _entree(con, ids, "Combien Jean Martin a-t-il payé ?")
    for suite in (["P:99", "FIN"], ["P:0"], ["P:0", "P:1", "FIN"]):
        rep = _verifier(con, e, suite)
        assert rep.erreur and [b.style for b in rep.blocs] == ["erreur"]
        actions = con.execute("SELECT actions FROM trace WHERE reponse_id = ?",
                              (rep.reponse_id,)).fetchone()[0]  # fmt: skip
        assert json.loads(actions)["erreur"] == rep.erreur


def test_trace_de_la_recherche_completee(stock):
    con, ids = stock
    con.execute("INSERT INTO trace (reponse_id, question) VALUES ('r1', 'q')")
    e = _entree(con, ids, "Combien Jean Martin a-t-il payé ?")
    e = Entree(e.ex, e.valeurs, e.question, conv_id=e.conv_id, reponse_id="r1")
    rep = _verifier(con, e, ["ABSTENTION", "FIN"], modele="oracle")
    assert rep.reponse_id == "r1"
    assert rep.texte == R.ABSTENTION
    assert con.execute("SELECT COUNT(*), MAX(modele) FROM trace").fetchone() == (1, "oracle")


def test_doublons_listes_et_plafonnes(stock):
    con, ids = stock
    # Copies de a1 dans les pièces D à G ; a1 est la version gardée.
    copies = [ajouter_piece(con, x, f"{x}.pdf", x, TypePiece.PV_AUDITION, 1, 2,
                            [(2, TEXTES["A"][1], GenreProposition.PHRASE, 0.7)], [])[0]
              for x in "DEFG"]  # fmt: skip
    con.executemany("UPDATE proposition SET groupe_doublon = ? WHERE prop_id = ?",
                    [(ids["a1"], p) for p in [ids["a1"], *copies]])  # fmt: skip
    e = _entree(con, ids, "Combien Jean Martin a-t-il payé ?")
    rep = _verifier(con, e, ["P:0", "ET", "P:1", "FIN"])
    textes = [b.texte for b in rep.blocs]
    attendu = ("Aussi dans : pièce D, page 2 ; pièce E, page 2 ; pièce F, page 2, "
               "et 1 autre endroit.")  # fmt: skip
    assert textes[2] == attendu  # sous [1], une seule fois (pas dans le bloc conflit ajouté)
    assert textes.count(attendu) == 1 and "pièce G" not in rep.texte
    con.execute("UPDATE proposition SET groupe_doublon = NULL WHERE prop_id = ?", (copies[-1],))
    rep = _verifier(con, e, ["P:0", "FIN"])
    assert "Aussi dans : pièce D, page 2 ; pièce E, page 2 ; pièce F, page 2." in rep.texte


# --- Suites de référence du corpus synthétique ------------------------------------------


def _questions(i):
    d = rediger_dossier(generer_monde(i, "entrainement", WCFG, frozenset()), WCFG)
    con = stock_de_reference(d, CFG)
    for q in poser_questions(d, WCFG):
        ex, valeurs = exemple_de_reference(d, q, con, CFG)
        hist = tuple(message_de_reference(t, CFG) for t in q.historique if t.texte)
        yield d, q, con, Entree(ex, valeurs, message_de_reference(q.message, CFG), hist)


@pytest.mark.parametrize("i", [0, 10, 50])
def test_suites_de_reference(i):
    vus = set()
    for d, q, con, e in _questions(i):
        suite = cible_de_reference(d, q, con, e.ex, CFG)
        rep = _verifier(con, e, suite)
        assert rep.erreur is None, (q.id, rep.erreur)
        for p in rep.citees:
            assert con.execute("SELECT texte FROM proposition WHERE prop_id = ?",
                               (p,)).fetchone()[0] in rep.texte  # fmt: skip
        if q.calcul:
            r = R.ecrire_valeur(q.calcul.unite, Fraction(Decimal(q.calcul.resultat)), None, 2)
            assert any(b.style == "calcul" and b.texte.endswith(f" = {r}") for b in rep.blocs), (
                q.id, r, rep.texte)  # fmt: skip
        if q.abstention:
            assert rep.blocs[0].texte == R.ABSTENTION
        vus |= {b.style for b in rep.blocs}
    assert {"citation", "calcul", "connecteur", "identite"} <= vus
