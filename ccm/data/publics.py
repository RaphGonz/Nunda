"""Conversion des jeux publics en exemples de modèle (SPEC.md §12, §4).

Chaque exemple passe par un stock SQLite en mémoire et par les fonctions de l'inférence
(`ajouter_piece`, `propager_stock`, `dedoublonner`, `detecter_conflits`, `anonymiser`) ; la
cible est contrôlée par l'automate (`accepter`). La détection des noms, seule étape coûteuse,
est faite une fois par texte distinct et gardée dans un cache hors de git (il contient des
positions, jamais de surface). Une partie donne des fichiers Parquet de `lot` exemples.
"""

import hashlib
import json
import multiprocessing
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pysbd

from ccm.anonymize.exemple import Message, anonymiser
from ccm.anonymize.table import TableConversation
from ccm.config import DonneesConfig, GrammarConfig, IngestConfig, load_config
from ccm.grammar.automaton import Contexte, accepter
from ccm.grammar.lexicon import OPERATEURS
from ccm.graph.store import ajouter_nombres, ajouter_piece
from ccm.ingest.conflicts import detecter_conflits
from ccm.ingest.dedup import dedoublonner
from ccm.ingest.numbers import NombreLu, nombres
from ccm.ner.detectors import Zone
from ccm.ner.propagate import detecter_message, ecrire_mentions, propager_stock
from ccm.ner.union import detecter
from ccm.schema import (
    Detecteur,
    Exemple,
    GenreNombre,
    GenreProposition,
    MarqueNombre,
    PrecisionDate,
    TypeArete,
    TypeNom,
    TypePiece,
    ouvrir_stock,
)


class Rejet(Exception):
    """L'exemple ne se convertit pas ; le message, sans donnée, va au bilan."""


@dataclass(frozen=True)
class Brut:
    """Une question d'un jeu public. `justificatives` : (paragraphe, phrase). `temoins` :
    chaînes qui ne doivent pas rester dans le texte (titres d'articles), jamais écrites."""

    id: str
    origine: str
    langue: str
    question: str
    paragraphes: list[list[str]]
    justificatives: list[tuple[int, int]] = field(default_factory=list)
    abstention: bool = False
    postfixe: list[str] | None = None
    genres: list[GenreProposition] | None = None  # genre de chaque paragraphe
    temoins: list[str] = field(default_factory=list)


# Nombres et dates de l'anglais (les formats de `ingest.numbers` sont français : « 5,829 »
# s'y lirait 5,829 et non 5 829).
_MOIS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
         "october", "november", "december")  # fmt: skip
_M = "|".join(_MOIS)
_DATES = re.compile(
    rf"(?<!\w)(?:((?i:{_M}))\s+(\d{{1,2}}),?\s+(\d{{4}})|(\d{{1,2}})\s+((?i:{_M})),?\s+(\d{{4}})"
    rf"|((?i:{_M}))\s+(\d{{4}}))(?!\w)"
)
_NOMBRE = re.compile(r"(?<![\w.,/])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(\s?%)?(?![\w])")


def nombres_en(texte: str, exclus: Iterable[tuple[int, int]], annee_min: int, annee_max: int
               ) -> list[NombreLu]:  # fmt: skip
    pris = list(exclus)
    out = []

    def libre(d: int, f: int) -> bool:
        return not any(a < f and d < b for a, b in pris)

    for m in _DATES.finditer(texte):
        if not libre(*m.span()):
            continue
        mois = (m[1] or m[5] or m[7]).lower()
        jour, an = m[2] or m[4], m[3] or m[6] or m[8]
        try:
            date(int(an), _MOIS.index(mois) + 1, int(jour or 1))
        except ValueError:  # « February 30, 2010 » : pas une date, ses nombres restent
            continue
        iso = f"{an}-{_MOIS.index(mois) + 1:02d}" + (f"-{int(jour):02d}" if jour else "")
        precision = PrecisionDate.JOUR if jour else PrecisionDate.MOIS
        out.append(NombreLu(*m.span(), m[0], GenreNombre.DATE, iso, "date", precision))
        pris.append(m.span())
    for m in _NOMBRE.finditer(texte):
        if not libre(*m.span()):
            continue
        s = m[1].replace(",", "")
        if not m[2] and s.isdigit() and len(s) == 4 and annee_min <= int(s) <= annee_max:
            lu = NombreLu(*m.span(), m[0], GenreNombre.DATE, s, "date", PrecisionDate.ANNEE)
        else:
            lu = NombreLu(*m.span(), m[0], GenreNombre.NUM, str(Decimal(s)), "%" if m[2] else "")
        out.append(lu)
    return sorted(out, key=lambda n: n.debut)


def _nombres(texte: str, exclus, langue: str, cfg: IngestConfig) -> list[NombreLu]:
    if langue == "en":
        return nombres_en(texte, exclus, cfg.nombres.annee_min, cfg.nombres.annee_max)
    return nombres(texte, cfg.nombres, exclus)


def phrases(texte: str, langue: str) -> list[tuple[int, str]]:
    """(début, phrase sans blancs de bord) ; `clean=False` : le texte n'est pas modifié."""
    out = []
    for s in pysbd.Segmenter(language=langue, clean=False, char_span=True).segment(texte):
        p = s.sent.strip()
        if p:
            out.append((s.start + s.sent.index(p), p))
    return out


# Cache des zones : clé = SHA-1 du texte.
def _cle(texte: str) -> str:
    return hashlib.sha1(texte.encode("utf-8")).hexdigest()


def _ouvrir_cache(chemin: Path) -> sqlite3.Connection:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(chemin)
    con.execute("CREATE TABLE IF NOT EXISTS zones (cle TEXT PRIMARY KEY, valeur TEXT)")
    return con


def remplir_cache(textes: Iterable[str], chemin: Path, cfg: IngestConfig, lot: int) -> int:
    """Détecte les textes absents du cache, par lots ; reprend là où il s'est arrêté."""
    con = _ouvrir_cache(chemin)
    vus = {k for (k,) in con.execute("SELECT cle FROM zones")}
    manquants = {}
    for t in textes:
        k = _cle(t)
        if k not in vus:
            manquants[k] = t
    ordre = sorted(manquants, key=lambda k: len(manquants[k]))  # lots GPU de longueur voisine
    for i in range(0, len(ordre), lot):
        cles = ordre[i : i + lot]
        zones = detecter([manquants[k] for k in cles], cfg)
        con.executemany(
            "INSERT OR REPLACE INTO zones VALUES (?, ?)",
            [(k, json.dumps([[z.debut, z.fin, str(z.type), sorted(map(str, z.detecteurs))]
                             for z in zs])) for k, zs in zip(cles, zones, strict=True)],
        )  # fmt: skip
        con.commit()
        print(f"détection : {min(i + lot, len(ordre))} / {len(ordre)}", flush=True)
    con.close()
    return len(ordre)


def _zones(valeur: str) -> list[Zone]:
    return [Zone(d, f, TypeNom(t), frozenset(Detecteur(x) for x in ds))
            for d, f, t, ds in json.loads(valeur)]  # fmt: skip


def textes_de(b: Brut) -> Iterator[str]:
    yield b.question
    for par in b.paragraphes:
        yield from par


def convertir(b: Brut, zones_de, cfg: IngestConfig, gcfg: GrammarConfig, graine: int
              ) -> tuple[Exemple, dict[int, str]]:  # fmt: skip
    """Exemple et valeurs (valeur_id → valeur) de la question. Rejet si elle ne convient pas."""
    con = ouvrir_stock(":memory:")
    ids = []
    for i, par in enumerate(b.paragraphes):
        genre = b.genres[i] if b.genres else GenreProposition.PHRASE
        ids.append(ajouter_piece(
            con, f"p{i}", "", _cle(f"{b.id}/{i}"), TypePiece.AUTRE, 0, 1,
            [(1, t, genre, 1.0) for t in par],
            [(k, k + 1, TypeArete.SUIVANTE) for k in range(len(par) - 1)],
        ))  # fmt: skip
    for par, pids in zip(b.paragraphes, ids, strict=True):
        for t, pid in zip(par, pids, strict=True):
            zs = zones_de(t)
            ecrire_mentions(con, pid, t, zs, cfg)
            ajouter_nombres(con, pid, _nombres(t, [(z.debut, z.fin) for z in zs], b.langue, cfg))
    propager_stock(con, cfg)
    dedoublonner(con, cfg.doublons)
    detecter_conflits(con, cfg)
    zq = detecter_message(b.question, con, cfg, zones=zones_de(b.question))
    msg = Message(
        b.question,
        tuple((z.debut, z.fin, z.type) for z in zq),
        tuple(_nombres(b.question, [(z.debut, z.fin) for z in zq], b.langue, cfg)),
    )
    tous = [p for pids in ids for p in pids]
    if len(tous) > 150:
        raise Rejet("plus de 150 propositions")
    table = TableConversation(graine, cfg.anonymiseur.reservoir)
    ex = anonymiser(con, tous, msg, table, cfg, id=b.id, origine=b.origine)
    con.close()
    # L'anonymiseur a écrit chaque nombre ; ses valeurs servent aux opérandes.
    valeurs = table.valeurs()
    local = {p.prop_id: p.local for p in ex.propositions}
    justifs = []
    for i, j in b.justificatives:
        if i >= len(ids) or j >= len(ids[i]):
            raise Rejet("justificative hors du contexte")
        if local[ids[i][j]] not in justifs:
            justifs.append(local[ids[i][j]])
    if b.abstention:
        cible = ["ABSTENTION", "FIN"]
    else:
        if not justifs:
            raise Rejet("aucune justificative")
        cible = []
        for k in justifs:
            cible += (["ET"] if cible else []) + [f"P:{k}"]
        if b.postfixe:
            cible += ["DONC", "CALCUL", *_operandes(b.postfixe, ex, justifs, valeurs), "FIN_CALCUL"]
        cible.append("FIN")
    ex = Exemple.model_validate(
        {
            **ex.model_dump(mode="json"),
            "langue": b.langue,
            "cible": cible,
            "justificatives": justifs,
        }
    )
    ctx = Contexte.depuis_exemple(ex, valeurs, cfg.conflits.negation)
    if not accepter(ctx, cible, gcfg):
        raise Rejet("refusé par l'automate")
    return ex, valeurs


def _operandes(postfixe: list[str], ex: Exemple, justifs: list[int], valeurs: dict[int, str]
               ) -> list[str]:  # fmt: skip
    """Chaque opérande devient N:k.j : le nombre de même valeur dans une justificative."""
    props = {p.local: p for p in ex.propositions}
    out = []
    for x in postfixe:
        if x in OPERATEURS:
            out.append(x)
            continue
        v = Decimal(x)
        for k in justifs:
            j = next((j for j, m in enumerate(props[k].marques)
                      if isinstance(m, MarqueNombre) and m.genre == "NUM"
                      and Decimal(valeurs[m.valeur_id]) == v), None)  # fmt: skip
            if j is not None:
                out.append(f"N:{k}.{j}")
                break
        else:
            raise Rejet("opérande absent des justificatives")
    return out


# Exécution : les détections sont lues dans le cache par chaque processus.
_etat: dict = {}


def _init(cache: str, graine: int) -> None:
    con = sqlite3.connect(f"file:{cache}?mode=ro", uri=True)
    _etat.update(con=con, graine=graine, cfg=load_config("ingest"), gcfg=load_config("grammar"))


def _zones_cache(t: str) -> list[Zone]:
    r = _etat["con"].execute("SELECT valeur FROM zones WHERE cle = ?", (_cle(t),)).fetchone()
    return _zones(r[0])


def _traiter(args: tuple[int, Brut]) -> tuple:
    i, b = args
    try:
        ex, valeurs = convertir(b, _zones_cache, _etat["cfg"], _etat["gcfg"], _etat["graine"] + i)
    except Rejet as e:
        return (None, str(e))
    except Exception as e:  # seul le type : le message pourrait citer un nom
        return (None, f"erreur {type(e).__name__}")
    # Un titre d'article resté en clair est un nom écrit : l'exemple n'est pas gardé (§15).
    texte = " ".join((ex.question.texte, *(p.texte for p in ex.propositions)))
    if any(t in texte for t in b.temoins):
        return (None, "titre resté en clair")
    return ((ex.id, ex.origine, ex.langue, ex.model_dump_json(), json.dumps(valeurs)), "")


_SCHEMA = pa.schema([("id", pa.string()), ("origine", pa.string()), ("langue", pa.string()),
                     ("exemple", pa.string()), ("valeurs", pa.string())])  # fmt: skip


def _ecrire(lignes: list[tuple], dossier: Path, n: int) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    colonnes = list(zip(*lignes, strict=True))
    table = pa.Table.from_arrays([pa.array(c, pa.string()) for c in colonnes], schema=_SCHEMA)
    pq.write_table(table, dossier / f"lot-{n:05d}.parquet", compression="zstd")


def convertir_partie(
    bruts: list[Brut], sortie: Path, cache: Path, cfg: DonneesConfig, processus: int
) -> dict:
    """Écrit `sortie/lot-*.parquet` ; rend le bilan (comptes, rejets par raison)."""
    rejets: Counter = Counter()
    lignes, lots, gardes = [], 0, 0
    entrees = list(enumerate(bruts))
    with multiprocessing.Pool(processus, _init, (str(cache), cfg.graine)) as pool:
        for ligne, raison in pool.imap(_traiter, entrees, chunksize=64):
            if ligne is None:
                rejets[raison] += 1
                continue
            gardes += 1
            lignes.append(ligne)
            if len(lignes) == cfg.lot_parquet:
                _ecrire(lignes, sortie, lots)
                lots += 1
                lignes = []
            if gardes % 5000 == 0:
                print(
                    f"{sortie.name} : {gardes} gardés, {sum(rejets.values())} rejetés", flush=True
                )
    if lignes:
        _ecrire(lignes, sortie, lots)
        lots += 1
    return {"entrees": len(bruts), "gardes": gardes, "lots": lots, "rejets": dict(rejets)}
