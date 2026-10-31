"""Propagation des noms et messages de l'utilisateur (SPEC.md §6).

Propagation : une chaîne détectée une fois dans une base est masquée partout dans cette
base (occurrence exacte, entre deux limites de mot). Message de l'utilisateur : même
détection, plus une recherche sans casse ni accents des normes déjà connues de la base
(« dupont » pour « Dupont ») et de chacun de leurs mots (« dupont » pour « Jean Dupont »),
sauf mots courts, titres, particules, mots vides et mots courants des lexiques.
"""

import re
import sqlite3

from ccm.anonymize.names import norme
from ccm.config import IngestConfig
from ccm.graph.store import ajouter_mentions
from ccm.ingest.racines import sans_accents
from ccm.ner.detectors import Zone, _courant
from ccm.ner.union import _type, detecter, unir
from ccm.schema import Detecteur, TypeNom

_PROPAGATION = frozenset({Detecteur.PROPAGATION})


def _nouvelle(zs: list[Zone], debut: int, fin: int, type_: TypeNom) -> bool:
    """Vrai si aucune zone ne contient déjà (debut, fin) avec un type au moins aussi
    prioritaire : un nom connu PER, déjà vu AUTRE par D4, reprend le type PER."""
    return not any(z.debut <= debut and fin <= z.fin and _type(z.type, type_) == z.type for z in zs)


def _trouver(texte: str, motif: re.Pattern, types: dict[str, TypeNom], zs: list[Zone]):
    for m in motif.finditer(texte):
        if _nouvelle(zs, *m.span(), types[m.group()]):
            yield Zone(*m.span(), types[m.group()], _PROPAGATION)


def propager(textes: list[str], zones: list[list[Zone]], longueur_min: int) -> list[list[Zone]]:
    """Ajoute aux zones de chaque texte toute occurrence d'une chaîne détectée ailleurs."""
    types: dict[str, TypeNom] = {}
    for t, zs in zip(textes, zones, strict=True):
        for z in zs:
            s = t[z.debut : z.fin]
            if len(s) >= longueur_min:
                types[s] = _type(types[s], z.type) if s in types else z.type
    if not types:
        return zones
    alternatives = "|".join(re.escape(s) for s in sorted(types, key=len, reverse=True))
    motif = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")
    return [
        unir(zs + list(_trouver(t, motif, types, zs))) for t, zs in zip(textes, zones, strict=True)
    ]


def _lignes_mentions(z: Zone, texte: str, cfg: IngestConfig) -> tuple:
    s = texte[z.debut : z.fin]
    detecteurs = ",".join(sorted(z.detecteurs))
    return (z.debut, z.fin, s, norme(s, cfg.noms), str(z.type), detecteurs)


def ecrire_mentions(con: sqlite3.Connection, prop_id: int, texte: str, zones, cfg) -> None:
    ajouter_mentions(con, prop_id, [_lignes_mentions(z, texte, cfg) for z in zones])


def propager_stock(con: sqlite3.Connection, cfg: IngestConfig) -> int:
    """Propagation sur tout le stock ; réécrit les mentions des propositions changées et
    retire les nombres qu'elles recouvrent. Rend le nombre de propositions changées."""
    props = con.execute("SELECT prop_id, texte FROM proposition ORDER BY prop_id").fetchall()
    zones: dict[int, list[Zone]] = {p: [] for p, _ in props}
    for p, d, f, t, ds in con.execute("SELECT prop_id, debut, fin, type, detecteurs FROM mention"):
        zones[p].append(Zone(d, f, TypeNom(t), frozenset(Detecteur(x) for x in ds.split(","))))
    ids = [p for p, _ in props]
    textes = [t for _, t in props]
    avant = [sorted(zones[p], key=lambda z: z.debut) for p in ids]
    apres = propager(textes, avant, cfg.detection.propagation_min)
    changees = 0
    for p, t, a, b in zip(ids, textes, avant, apres, strict=True):
        if a == b:
            continue
        changees += 1
        con.execute("DELETE FROM mention WHERE prop_id = ?", (p,))
        ecrire_mentions(con, p, t, b, cfg)
        for z in b:
            con.execute(
                "DELETE FROM nombre WHERE prop_id = ? AND debut < ? AND fin > ?",
                (p, z.fin, z.debut),
            )
    return changees


def _plier(texte: str) -> tuple[str, list[int]]:
    """Texte sans casse ni accents, tirets et blancs en espace ; position d'origine de
    chaque caractère plié."""
    plie, pos = [], []
    for i, c in enumerate(texte):
        for x in sans_accents(c.casefold()):
            plie.append(" " if re.fullmatch(r"[-‐–\s]", x) else x)
            pos.append(i)
    return "".join(plie), pos


def connus(con: sqlite3.Connection, cfg: IngestConfig) -> dict[str, TypeNom]:
    """Normes connues de la base et leur type (le plus prioritaire)."""
    types: dict[str, TypeNom] = {}
    for n, t in con.execute("SELECT DISTINCT norme, type FROM mention"):
        if len(n) >= cfg.detection.propagation_min:
            types[n] = _type(types[n], TypeNom(t)) if n in types else TypeNom(t)
    return types


def mots_connus(con: sqlite3.Connection, cfg: IngestConfig, types: dict[str, TypeNom]):
    """Chaque mot d'au moins 3 lettres des normes connues `types`, sauf titres, particules,
    mots vides et mots courants. Le lexique se lit sur le mot écrit, avec ses accents
    (« société », pas « societe »)."""
    fixes = {*cfg.noms.titres, *cfg.noms.particules, *cfg.racines.mots_vides}
    out: dict[str, TypeNom] = {}
    for s, n, t in con.execute("SELECT DISTINCT surface, norme, type FROM mention"):
        if n not in types:
            continue
        for mot in re.split(r"[-‐–\s]+", s):
            w = norme(mot, cfg.noms)
            if len(w) < 3 or w in fixes or _courant(mot, cfg.detection.lexiques):
                continue
            out[w] = _type(out[w], TypeNom(t)) if w in out else TypeNom(t)
    return out


def chercher_connus(texte: str, types: dict[str, TypeNom], zones: list[Zone]) -> list[Zone]:
    """Zones nouvelles des chaînes `types`, cherchées sans casse ni accents, tirets et
    blancs égaux."""
    if not types:
        return []
    plie, pos = _plier(texte)
    alternatives = "|".join(
        re.escape(n).replace(" ", " +") for n in sorted(types, key=len, reverse=True)
    )
    trouvees = []
    for m in re.finditer(rf"(?<!\w)(?:{alternatives})(?!\w)", plie):
        n = re.sub(" +", " ", m.group())
        debut, fin = pos[m.start()], pos[m.end() - 1] + 1
        if _nouvelle(zones, debut, fin, types[n]):
            trouvees.append(Zone(debut, fin, types[n], _PROPAGATION))
    return trouvees


def detecter_message(
    texte: str, con: sqlite3.Connection, cfg: IngestConfig, zones: list[Zone] | None = None
) -> list[Zone]:
    """Zones de noms d'un message : détecteurs (ou `zones`, déjà détectées), plus les normes
    connues de la base."""
    zones = detecter([texte], cfg)[0] if zones is None else zones
    types = connus(con, cfg)
    types = {**mots_connus(con, cfg, types), **types}
    return unir(zones + chercher_connus(texte, types, zones))
