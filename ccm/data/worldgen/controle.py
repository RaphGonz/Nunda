"""Contrôle de provenance des pièces synthétiques (SPEC.md §12, « Contrôle »).

Chaque nom, nombre et date d'une ligne doit appartenir aux faits déclarés de la ligne,
et chaque fait déclaré doit être vrai dans le monde : un participant de l'événement
(dans sa version), son lieu, sa société, sa date, son heure, ses montants ; ou, pour
une ligne sans événement, une personne, une société, une date ou la référence de la
pièce. Les surfaces sont relues par des analyseurs écrits ici, sans le code de
rédaction. Le texte hors des faits ne doit contenir ni chiffre, ni mois, ni nom du
monde, ni mot à majuscule absent du texte fixe des gabarits. Le PDF doit rendre le
texte de chaque ligne. Une pièce avec une erreur est rejetée.
"""

import re
from datetime import date, time
from decimal import Decimal
from functools import cache

import pymupdf

from ccm.data.worldgen.pieces import (
    MOIS,
    TEXTE_CODE,
    Dossier,
    Fait,
    Ligne,
    Piece,
    forme_personne,
    forme_societe,
    gabarits,
)

_MOT = re.compile(r"[^\W\d_]+")
_MONTANT = re.compile(r"^(\d{1,3}(?: \d{3})+|\d+)(?:,(\d{2}))? (?:€|euros)$")
_DATE_CHIFFRES = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_DATE_LETTRES = re.compile(rf"^(1er|\d{{1,2}}) ({'|'.join(MOIS)}) (\d{{4}})$")
_HEURE = re.compile(r"^(\d{1,2})(?: h (\d{2})| h|h(\d{2})|:(\d{2}))$")


def lire_montant(s: str) -> Decimal | None:
    m = _MONTANT.match(s)
    if not m:
        return None
    return Decimal(m[1].replace(" ", "")) + Decimal(m[2] or 0) / 100


def lire_date(s: str) -> date | None:
    if m := _DATE_CHIFFRES.match(s):
        j, mois, a = int(m[1]), int(m[2]), int(m[3])
    elif m := _DATE_LETTRES.match(s):
        j = 1 if m[1] == "1er" else int(m[1])
        mois, a = MOIS.index(m[2]) + 1, int(m[3])
    else:
        return None
    try:
        return date(a, mois, j)
    except ValueError:
        return None


def lire_heure(s: str) -> time | None:
    m = _HEURE.match(s)
    if not m:
        return None
    minutes = next((x for x in m.groups()[1:] if x is not None), "0")
    try:
        return time(int(m[1]), int(minutes))
    except ValueError:
        return None


@cache
def vocabulaire(reservoir: str) -> frozenset[str]:
    """Mots du texte fixe : gabarits du réservoir (champs retirés) et texte du code."""
    textes: list[str] = [TEXTE_CODE]

    def parcourir(x):
        if isinstance(x, str):
            textes.append(re.sub(r"\{\w+\}", " ", x))
        elif isinstance(x, dict):
            for v in x.values():
                parcourir(v)
        else:
            for v in x:
                parcourir(v)

    parcourir(gabarits(reservoir))
    return frozenset(w for t in textes for w in _MOT.findall(t))


def _noms_du_monde(d: Dossier) -> set[str]:
    m = d.monde
    mots = set()
    for chaine in (
        [p.prenom for p in m.personnes]
        + [p.nom for p in m.personnes]
        + [p.surnom for p in m.personnes if p.surnom]
        + [s.nom for s in m.societes]
        + [x.nom for x in m.lieux]
    ):
        mots |= {w for w in _MOT.findall(chaine) if w[0].isupper()}
    return mots


def _permis(d: Dossier, piece: Piece, ligne: Ligne) -> dict[str, set]:
    """Valeurs que les faits de la ligne ont le droit de porter."""
    if ligne.evenement is not None:
        if ligne.evenement not in piece.evenements:
            return {}
        e = d.evenement(ligne.evenement, ligne.version)
        return {
            "PER": set(e.participants),
            "ORG": set(e.societes),
            "LIEU": {e.lieu},
            "NUM": {str(v.quantize(Decimal("0.01"))) for v in e.montants},
            "DATE": {e.date.isoformat()},
            "HEURE": {f"{e.heure:%H:%M}"},
            "REF": set(),
        }
    personnes = {piece.auteur, piece.locuteur, piece.signataire} - {None}
    return {
        "PER": personnes,
        "ORG": {piece.expediteur} - {None},
        "LIEU": set(),
        "NUM": set(),
        "DATE": {x.isoformat() for x in (piece.date, *piece.periode)},
        "HEURE": set(),
        "REF": {piece.reference},
    }


def _fait(d: Dossier, f: Fait, permis: dict[str, set]) -> str | None:
    m = d.monde
    if f.genre in ("PER", "ORG", "LIEU"):
        if f.entite not in permis[f.genre]:
            return f"{f.genre} {f.entite} hors des faits de la ligne"
        if f.genre == "PER":
            attendu = forme_personne(m.personnes[f.entite], f.forme)
        elif f.genre == "ORG":
            attendu = forme_societe(m.societes[f.entite], f.forme)
        else:
            attendu = m.lieux[f.entite].nom
        return None if f.surface == attendu else f"surface {f.surface!r} ≠ {attendu!r}"
    if f.valeur not in permis[f.genre]:
        return f"{f.genre} {f.valeur} hors des faits de la ligne"
    lu = {
        "REF": lambda s: s,
        "NUM": lambda s: (v := lire_montant(s)) is not None and str(v.quantize(Decimal("0.01"))),
        "DATE": lambda s: (v := lire_date(s)) and v.isoformat(),
        "HEURE": lambda s: (v := lire_heure(s)) and f"{v:%H:%M}",
    }[f.genre](f.surface)
    if f.genre == "NUM" and f.unite != "€":
        return f"unité {f.unite!r}"
    return None if lu == f.valeur else f"surface {f.surface!r} relue {lu!r} ≠ {f.valeur}"


def controler_ligne(d: Dossier, piece: Piece, ligne: Ligne) -> list[str]:
    erreurs = []
    permis = _permis(d, piece, ligne)
    if not permis:
        return [f"événement {ligne.evenement} absent de la pièce"]
    reste, fin = [], 0
    for f in ligne.faits:
        if f.debut < fin or ligne.texte[f.debut : f.fin] != f.surface:
            erreurs.append(f"position de {f.surface!r}")
            continue
        if e := _fait(d, f, permis):
            erreurs.append(e)
        reste.append(ligne.texte[fin : f.debut])
        fin = f.fin
    reste.append(ligne.texte[fin:])
    hors = " | ".join(reste)
    if re.search(r"\d", hors):
        erreurs.append(f"chiffre non déclaré : {hors!r}")
    vocab = vocabulaire(d.monde.reservoir)
    noms = _noms_du_monde(d)
    for w in _MOT.findall(hors):
        if w.lower() in MOIS:
            erreurs.append(f"mois non déclaré : {w!r}")
        elif w in noms and w not in vocab:
            erreurs.append(f"nom non déclaré : {w!r}")
        elif w[0].isupper() and w not in vocab and w[0].lower() + w[1:] not in vocab:
            erreurs.append(f"mot à majuscule hors gabarit : {w!r}")
    return [f"{piece.id} « {ligne.texte} » : {e}" for e in erreurs]


def controler_piece(d: Dossier, piece: Piece) -> list[str]:
    erreurs = []
    for ligne in piece.lignes:
        erreurs += controler_ligne(d, piece, ligne)
    return erreurs


def controler_pdf(pdf: bytes, piece: Piece) -> list[str]:
    """Chaque ligne (chaque cellule d'un tableau) se relit dans le texte du PDF."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        texte = " ".join(" ".join(page.get_text().split()) for page in doc)
    erreurs = []
    for ligne in piece.lignes:
        bouts = ligne.texte.split(" | ") if ligne.genre == "LIGNE_TABLEAU" else [ligne.texte]
        for b in bouts:
            if " ".join(b.split()) not in texte:
                erreurs.append(f"{piece.id} : absent du PDF : {b!r}")
    return erreurs
