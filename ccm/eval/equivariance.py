"""T2 (SPEC.md §14) : renommage d'un dossier synthétique et forme canonique d'un exemple.

Stock de référence : les lignes du dossier deviennent les propositions, ses faits de nom
et de nombre deviennent les mentions et les nombres (aucun détecteur), puis les conflits
établis sont calculés (§5, étape 8).

Bijection qui garde les relations : une permutation des 26 lettres, appliquée à chaque
mot des noms (mots séparés par blancs et tirets), sans les accents, casse gardée. Restent
fixes les mots que les règles de §6 lisent comme du texte : titres et particules, et mots
vides écrits en minuscules. Elle garde la longueur des chaînes, l'égalité des normes, les
distances d'édition, les initiales et les inclusions de mots. Une permutation n'est
retenue que si elle n'a aucun point fixe (chaque lettre change) et qu'aucun mot renommé
ne devient un mot fixe.
"""

import random
import re
import sqlite3
import string

from ccm.anonymize.encode import ordre_apparition
from ccm.anonymize.exemple import Message
from ccm.anonymize.names import norme
from ccm.anonymize.relations import SYMETRIQUES
from ccm.config import IngestConfig
from ccm.data.worldgen.pieces import Dossier, Fait
from ccm.data.worldgen.questions import Question, Tour
from ccm.graph.store import ajouter_mentions, ajouter_nombres, ajouter_piece
from ccm.ingest.conflicts import detecter_conflits
from ccm.ingest.numbers import NombreLu
from ccm.ingest.racines import sans_accents
from ccm.schema import Exemple, GenreNombre, PrecisionDate, TypeArete, TypePiece, ouvrir_stock

GENRES_NOMS = ("PER", "ORG", "LIEU", "REF")
_PRECISION = {10: PrecisionDate.JOUR, 7: PrecisionDate.MOIS, 4: PrecisionDate.ANNEE}
_MOT = re.compile(r"[^-‐–\s]+")


# --- Stock de référence -------------------------------------------------------------


def _nombre(f: Fait, cfg: IngestConfig) -> NombreLu:
    if f.genre == "DATE":
        return NombreLu(f.debut, f.fin, f.surface, GenreNombre.DATE, f.valeur, "date",
                        _PRECISION[len(f.valeur)])  # fmt: skip
    if f.genre == "HEURE":
        h, m = f.valeur.split(":")
        u = cfg.nombres.unite_heure_du_jour
        return NombreLu(f.debut, f.fin, f.surface, GenreNombre.NUM, str(int(h) * 60 + int(m)), u)
    return NombreLu(f.debut, f.fin, f.surface, GenreNombre.NUM, f.valeur, f.unite or "")


def stock_de_reference(d: Dossier, cfg: IngestConfig) -> sqlite3.Connection:
    con = ouvrir_stock(":memory:")
    for p in d.pieces:
        type_ = TypePiece(p.type) if p.type in TypePiece.__members__ else TypePiece.AUTRE
        n = len(p.lignes)
        ids = ajouter_piece(
            con, p.id, f"{p.id}.pdf", p.id, type_, cfg.pieces.rang.get(type_, 0), 1,
            [(1, li.texte, li.genre, 1.0) for li in p.lignes],
            [(k, k + 1, TypeArete.SUIVANTE) for k in range(n - 1)],
        )  # fmt: skip
        for pid, li in zip(ids, p.lignes, strict=True):
            noms = [f for f in li.faits if f.genre in GENRES_NOMS]
            ajouter_mentions(con, pid, [(f.debut, f.fin, f.surface, norme(f.surface, cfg.noms),
                                         f.genre, "reference") for f in noms])  # fmt: skip
            ajouter_nombres(con, pid, [_nombre(f, cfg) for f in li.faits if f.genre in
                                       ("NUM", "DATE", "HEURE")])  # fmt: skip
    detecter_conflits(con, cfg)
    return con


def message_de_reference(t: Tour, cfg: IngestConfig) -> Message:
    return Message(
        t.texte,
        tuple((f.debut, f.fin, f.genre) for f in t.faits if f.genre in GENRES_NOMS),
        tuple(_nombre(f, cfg) for f in t.faits if f.genre in ("NUM", "DATE", "HEURE")),
    )


# --- Bijection ----------------------------------------------------------------------


def _fixe(mot: str, cfg: IngestConfig) -> bool:
    n = norme(mot, cfg.noms)
    return (
        n.rstrip(".") in cfg.noms.titres
        or n in cfg.noms.particules
        or (mot.islower() and n in cfg.racines.mots_vides)
    )


def _lettre(c: str, perm: dict[str, str]) -> str:
    b = sans_accents(c)
    if len(b) == 1 and b.lower() in perm:
        r = perm[b.lower()]
        return r.upper() if b.isupper() else r
    return c


def _renommer_mot(mot: str, perm: dict[str, str]) -> str:
    return "".join(_lettre(c, perm) for c in mot)


def renommer(s: str, perm: dict[str, str], cfg: IngestConfig) -> str:
    return _MOT.sub(
        lambda m: m.group() if _fixe(m.group(), cfg) else _renommer_mot(m.group(), perm), s
    )


def _surfaces(d: Dossier, questions: tuple[Question, ...]) -> set[str]:
    tours = [t for q in questions for t in (q.message, *q.historique)]
    lignes = [li for p in d.pieces for li in p.lignes]
    return {f.surface for x in (*lignes, *tours) for f in x.faits if f.genre in GENRES_NOMS}


def bijection(d: Dossier, questions: tuple[Question, ...], cfg: IngestConfig) -> dict[str, str]:
    """Première permutation sans point fixe (graines 0, 1, …) sous laquelle aucun mot
    renommé d'un nom ne devient un mot fixe."""
    mots = {m for s in _surfaces(d, questions) for m in _MOT.findall(s) if not _fixe(m, cfg)}
    for graine in range(10_000):
        lettres = list(string.ascii_lowercase)
        random.Random(graine).shuffle(lettres)
        perm = dict(zip(string.ascii_lowercase, lettres, strict=True))
        if any(a == b for a, b in perm.items()):
            continue
        if not any(_fixe(_renommer_mot(m, perm), cfg) for m in mots):
            return perm
    raise ValueError("aucune permutation valide")


def _renommer_faits(texte: str, faits, perm, cfg) -> tuple[str, tuple]:
    out = []
    for f in faits:
        if f.genre in GENRES_NOMS:
            s = renommer(f.surface, perm, cfg)
            texte = texte[: f.debut] + s + texte[f.fin :]
            f = f.model_copy(update=dict(surface=s))
        out.append(f)
    return texte, tuple(out)


def renommer_tour(t: Tour, perm: dict[str, str], cfg: IngestConfig) -> Tour:
    texte, faits = _renommer_faits(t.texte, t.faits, perm, cfg)
    return t.model_copy(update=dict(texte=texte, faits=faits))


def renommer_dossier(d: Dossier, perm: dict[str, str], cfg: IngestConfig) -> Dossier:
    pieces = []
    for p in d.pieces:
        lignes = []
        for li in p.lignes:
            texte, faits = _renommer_faits(li.texte, li.faits, perm, cfg)
            lignes.append(li.model_copy(update=dict(texte=texte, faits=faits)))
        pieces.append(p.model_copy(update=dict(lignes=tuple(lignes))))
    return d.model_copy(update=dict(pieces=tuple(pieces)))


# --- Forme canonique ----------------------------------------------------------------


def canonique(ex: Exemple) -> dict:
    """Exemple dont les indices de noms et de valeurs sont remplacés par leur rang de
    première apparition ; relations triées, symétriques dans l'ordre (petit, grand)."""
    noms, vals = ordre_apparition(ex)
    out = ex.model_dump(mode="json")
    for t in (*out["historique"], out["question"], *out["propositions"]):
        for m in t["marques"]:
            if m["genre"] == "NOM":
                m["nom"] = noms[m["nom"]]
            else:
                m["valeur_id"] = vals[m["valeur_id"]]
    rels = []
    for a, b, r in ex.relations_noms:
        a, b = noms[a], noms[b]
        rels.append([min(a, b), max(a, b), r] if r in SYMETRIQUES else [a, b, r])
    out["relations_noms"] = sorted(rels)
    return out
