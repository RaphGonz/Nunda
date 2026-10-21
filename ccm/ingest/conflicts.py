"""Étape 8 de l'ingestion : conflits établis (SPEC.md §5).

Le code ne crée une arête CONFLIT que dans deux cas.

A. Même fait, valeur différente. Deux propositions de pièces différentes ont une date au
   jour en commun, un nom en commun (nom de famille d'une mention PER, ou norme d'une
   mention ORG), un lieu en commun si les deux en ont un, un type d'acte en commun si les
   deux en ont un. Conflit si leurs heures du jour, alignées par ordre, diffèrent ; si
   leurs montants en euros se recouvrent en partie (un commun, un propre à chacune) ; ou
   si une seule contient une marque de négation, cherchée hors des mentions.
B. Versions d'un même article. Un article va d'une proposition qui commence par un
   en-tête d'article au prochain en-tête de la pièce. Clé : code cité (en-tête de
   l'article, sinon en-têtes de la pièce) et numéro normalisé ; la référence elle-même
   n'entre pas dans le texte comparé. Deux articles de même clé,
   dans deux pièces, aux textes différents : arête entre chaque proposition de l'un sans
   copie exacte dans l'autre et chaque proposition de l'autre sans copie exacte.

Les valeurs se comparent en décimal exact. Les doublons non gardés sont remplacés par leur
version gardée. L'arête est écrite dans les deux sens ; le calcul porte sur tout le stock
et remplace le précédent. Les types d'acte se lisent sur les racines (`ingest/racines.py`).
"""

import re
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import combinations

from ccm.anonymize.names import nom_famille, norme
from ccm.config import IngestConfig
from ccm.ingest.dedup import normaliser
from ccm.ingest.racines import racines
from ccm.schema import GenreNombre, PrecisionDate, TypeArete


class _Prop:
    __slots__ = ("piece", "texte", "jours", "heures", "euros", "noms", "lieux", "actes", "neg")

    def __init__(self, piece: str, texte: str):
        self.piece, self.texte = piece, texte
        self.jours: set[str] = set()
        self.heures: list[int] = []
        self.euros: list[Decimal] = []
        self.noms: set[tuple[str, str]] = set()
        self.lieux: set[str] = set()
        self.actes: set[str] = set()
        self.neg = False


def _hors_mentions(texte: str, zones) -> str:
    t = list(texte)
    for d, f in zones:
        t[d:f] = " " * (f - d)
    return "".join(t)


def _differentes(a: list, b: list) -> bool:
    return any(x != y for x, y in zip(a, b, strict=False))


def _recouvrement_partiel(a: list, b: list) -> bool:
    sa, sb = set(a), set(b)
    return bool(sa & sb) and bool(sa - sb) and bool(sb - sa)


def meme_fait(a: _Prop, b: _Prop) -> bool:
    return (
        a.piece != b.piece
        and bool(a.jours & b.jours)
        and bool(a.noms & b.noms)
        and (not a.lieux or not b.lieux or bool(a.lieux & b.lieux))
        and (not a.actes or not b.actes or bool(a.actes & b.actes))
    )


def en_conflit(a: _Prop, b: _Prop) -> bool:
    return meme_fait(a, b) and (
        _differentes(a.heures, b.heures)
        or _recouvrement_partiel(a.euros, b.euros)
        or a.neg != b.neg
    )


def _props(con: sqlite3.Connection, cfg: IngestConfig) -> dict[int, _Prop]:
    """Propositions gardées, avec leurs faits."""
    c = cfg.conflits
    props = {
        pid: _Prop(piece, texte)
        for pid, piece, texte in con.execute(
            "SELECT prop_id, piece_id, texte FROM proposition "
            "WHERE groupe_doublon IS NULL OR groupe_doublon = prop_id"
        )
    }
    for pid, g, v, u, pr in con.execute(
        "SELECT prop_id, genre, valeur, unite, precision_date FROM nombre ORDER BY prop_id, debut"
    ):
        p = props.get(pid)
        if p is None:
            continue
        if g == GenreNombre.DATE:
            if pr == PrecisionDate.JOUR:
                p.jours.add(v)
        elif u == cfg.nombres.unite_heure_du_jour:
            p.heures.append(int(v))
        elif u == c.unite_euro:
            p.euros.append(Decimal(v))
    zones = defaultdict(list)
    for pid, d, f, s, n, t in con.execute(
        "SELECT prop_id, debut, fin, surface, norme, type FROM mention"
    ):
        p = props.get(pid)
        if p is None:
            continue
        zones[pid].append((d, f))
        if t == "PER":
            if (famille := nom_famille(s, cfg.noms)) is not None:
                p.noms.add(("PER", famille))
        elif t == "ORG":
            p.noms.add(("ORG", n))
        elif t == "LIEU":
            p.lieux.add(n)
    actes = {t: set(racines(" ".join(mots), cfg.racines)) for t, mots in c.actes.items()}
    negations = [re.compile(m, re.IGNORECASE) for m in c.negation]
    for pid, p in props.items():
        texte = _hors_mentions(p.texte, zones[pid])
        r = set(racines(texte, cfg.racines))
        p.actes = {t for t, rs in actes.items() if r & rs}
        p.neg = any(m.search(texte) for m in negations)
    return props


def _conflits_faits(props: dict[int, _Prop]) -> set[tuple[int, int]]:
    par_jour = defaultdict(list)
    for pid, p in props.items():
        if p.noms:
            for j in p.jours:
                par_jour[j].append(pid)
    return {
        (a, b)
        for ids in par_jour.values()
        for a, b in combinations(sorted(ids), 2)
        if en_conflit(props[a], props[b])
    }


def _conflits_articles(con: sqlite3.Connection, cfg: IngestConfig) -> set[tuple[int, int]]:
    c = cfg.conflits
    motif, code = re.compile(c.motif_article), re.compile(c.motif_code)
    garde = {p: g or p for p, g in con.execute("SELECT prop_id, groupe_doublon FROM proposition")}
    code_piece = {}
    for piece, texte in con.execute(
        "SELECT piece_id, texte FROM proposition WHERE genre = 'EN_TETE' ORDER BY prop_id"
    ):
        if piece not in code_piece and (m := code.search(texte)):
            code_piece[piece] = norme(m.group(0), cfg.noms)
    articles = defaultdict(list)  # clé → [(pièce, [(prop_id, texte normalisé)])]
    courant = None
    for pid, piece, texte in con.execute(
        "SELECT prop_id, piece_id, texte FROM proposition ORDER BY piece_id, ordre"
    ):
        if courant is not None and courant[0] != piece:
            courant = None
        if m := motif.match(texte):
            numero = re.sub(r"[\s.]", "", m.group(1)).replace("–", "-").upper()
            cc = code.search(texte)
            cle = (norme(cc.group(0), cfg.noms) if cc else code_piece.get(piece), numero)
            courant = (piece, [])
            articles[cle].append(courant)
            texte = texte[m.end() :]  # la référence elle-même ne se compare pas
        if courant is not None and (t := normaliser(texte).strip(" :.-–")):
            courant[1].append((pid, t))
    paires = set()
    for versions in articles.values():
        for (pa, a), (pb, b) in combinations(versions, 2):
            if pa == pb:
                continue
            ta, tb = Counter(t for _, t in a), Counter(t for _, t in b)
            seuls_a = [garde[p] for p, t in a if t not in tb]
            seuls_b = [garde[p] for p, t in b if t not in ta]
            paires |= {tuple(sorted((x, y))) for x in seuls_a for y in seuls_b if x != y}
    return paires


def detecter_conflits(con: sqlite3.Connection, cfg: IngestConfig) -> int:
    """Recalcule les arêtes CONFLIT du stock ; rend le nombre de paires."""
    paires = _conflits_faits(_props(con, cfg)) | _conflits_articles(con, cfg)
    con.execute("DELETE FROM arete WHERE type = ?", (str(TypeArete.CONFLIT),))
    con.executemany(
        "INSERT INTO arete VALUES (?, ?, ?)",
        [(a, b, str(TypeArete.CONFLIT)) for p in sorted(paires) for a, b in (p, p[::-1])],
    )
    return len(paires)
