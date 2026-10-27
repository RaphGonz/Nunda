"""Exemple anonymisé (SPEC.md §4, §6) : la frontière entre le stock et le modèle.

Chaque mention de nom et chaque nombre devient un marqueur ⟦i⟧ et une marque (slot et
attributs). Les noms et les valeurs reçoivent leur indice de la table de la conversation,
dans l'ordre de première apparition : historique, question, puis propositions dans
l'ordre reçu. Le même code sert à l'entraînement et à l'inférence.
"""

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ccm.anonymize.names import norme
from ccm.anonymize.relations import Nom, alias_declares, genre_titre, relations_noms
from ccm.anonymize.table import TableConversation
from ccm.anonymize.units import attributs, cle_valeur
from ccm.config import IngestConfig
from ccm.ingest.numbers import NombreLu, nombres
from ccm.schema import (
    Exemple,
    MarqueNom,
    MarqueNombre,
    Proposition,
    Relation,
    TexteMarque,
    TypeArete,
    TypeNom,
    TypePiece,
)

_RELATIONS_ARETES = {
    TypeArete.SUIVANTE: Relation.SUIVANTE,
    TypeArete.DEPEND_DE: Relation.DEPEND_DE,
    TypeArete.CONFLIT: Relation.CONFLIT,
    TypeArete.DOUBLON_DE: Relation.DOUBLON_DE,
}


@dataclass(frozen=True)
class Message:
    """Message de l'utilisateur (ou du modèle, dans l'historique), avec ses zones."""

    texte: str
    noms: tuple[tuple[int, int, TypeNom], ...]  # (début, fin, type)
    nombres: tuple[NombreLu, ...]


def lire_message(texte: str, con: sqlite3.Connection, cfg: IngestConfig) -> Message:
    """Détection d'un message : détecteurs, noms connus de la base sans casse, nombres."""
    from ccm.ner.propagate import detecter_message

    zs = detecter_message(texte, con, cfg)
    exclus = [(z.debut, z.fin) for z in zs]
    return Message(
        texte,
        tuple((z.debut, z.fin, z.type) for z in zs),
        tuple(nombres(texte, cfg.nombres, exclus)),
    )


@dataclass(frozen=True)
class _Zone:
    debut: int
    fin: int
    cle: tuple  # ("NOM", norme, type) ou (genre, valeur, unité, précision)


def _zones(texte: str, noms, nbs, cfg: IngestConfig) -> list[_Zone]:
    """Noms (surface lue dans le texte) et nombres hors des noms, par position."""
    zs = [_Zone(d, f, ("NOM", norme(texte[d:f], cfg.noms), TypeNom(t))) for d, f, t in noms]
    for d, f, g, v, u, p in nbs:
        if not any(z.debut < f and d < z.fin for z in zs):
            zs.append(_Zone(d, f, (str(g), v, u, p)))
    return sorted(zs, key=lambda z: z.debut)


def zones_message(m: Message, cfg: IngestConfig) -> list[_Zone]:
    """Zones d'un message : la zone j est la marque j de son texte anonymisé."""
    return _zones(m.texte, m.noms, [(n.debut, n.fin, n.genre, n.valeur, n.unite, n.precision)
                                    for n in m.nombres], cfg)  # fmt: skip


def zones_propositions(
    con: sqlite3.Connection, prop_ids: Sequence[int], cfg: IngestConfig
) -> dict[int, tuple[str, list[_Zone]]]:
    """prop_id → (texte original, zones) ; la zone j est la marque j de la proposition."""
    marques = ",".join("?" * len(prop_ids))
    textes = dict(con.execute(
        f"SELECT prop_id, texte FROM proposition WHERE prop_id IN ({marques})", list(prop_ids)
    ))  # fmt: skip
    noms: dict[int, list] = {p: [] for p in textes}
    for p, d, f, t in con.execute(
        f"SELECT prop_id, debut, fin, type FROM mention WHERE prop_id IN ({marques})",
        list(prop_ids),
    ):
        noms[p].append((d, f, t))
    nbs: dict[int, list] = {p: [] for p in textes}
    for p, *n in con.execute(
        "SELECT prop_id, debut, fin, genre, valeur, unite, precision_date FROM nombre "
        f"WHERE prop_id IN ({marques})",
        list(prop_ids),
    ):
        nbs[p].append(tuple(n))
    return {p: (t, _zones(t, noms[p], nbs[p], cfg)) for p, t in textes.items()}


def _contraintes(con, conv_id, hypotheses) -> Iterable[tuple[str, str, Relation]]:
    if conv_id is not None:
        for g, a, b in con.execute(
            "SELECT genre, a_norme, b_norme FROM contrainte WHERE conv_id = ? "
            "AND genre IN ('MEME', 'DIFFERENT')",
            (conv_id,),
        ):
            yield a, b, Relation.MEME_UTILISATEUR if g == "MEME" else Relation.DIFFERENT_UTILISATEUR
    for a, b in hypotheses:
        yield a, b, Relation.MEME_HYPOTHESE


def anonymiser(
    con: sqlite3.Connection,
    prop_ids: Sequence[int],
    question: Message,
    table: TableConversation,
    cfg: IngestConfig,
    *,
    historique: Sequence[Message] = (),
    conv_id: str | None = None,
    hypotheses: Iterable[tuple[str, str]] = (),
    citees: frozenset[int] = frozenset(),
    id: str = "",
    origine: str = "stock",
) -> Exemple:
    """Exemple sans aucun nom : question, historique et propositions `prop_ids` du stock,
    dans cet ordre. `hypotheses` : normes des SAME non refusés des tours précédents."""
    marques = ",".join("?" * len(prop_ids))
    lignes = {
        r[0]: r
        for r in con.execute(
            "SELECT p.prop_id, p.piece_id, p.texte, p.ocr_conf, c.type, c.rang FROM proposition p "
            f"JOIN piece c USING (piece_id) WHERE p.prop_id IN ({marques})",
            list(prop_ids),
        )
    }
    zp = zones_propositions(con, prop_ids, cfg)
    textes = [m.texte for m in (*historique, question)] + [lignes[p][2] for p in prop_ids]
    zones = [zones_message(m, cfg) for m in (*historique, question)] + [zp[p][1] for p in prop_ids]

    # Noms et valeurs dans l'ordre de première apparition.
    locaux: dict[tuple, int] = {}
    surfaces: dict[tuple, set] = {}
    genres: dict[tuple, set] = {}
    valeurs: dict[tuple, None] = {}
    for texte, zs in zip(textes, zones, strict=True):
        for z in zs:
            if z.cle[0] == "NOM":
                locaux.setdefault(z.cle, len(locaux))
                surfaces.setdefault(z.cle, set()).add(texte[z.debut : z.fin])
                g = genre_titre(texte, z.debut, cfg.noms)
                genres.setdefault(z.cle, set()).update([g] if g else [])
            else:
                valeurs.setdefault(z.cle, None)
    cles_noms = list(locaux)
    indices = [table.nom(t, n) for _, n, t in cles_noms]
    attrs = dict(
        zip(valeurs, attributs([(g, v, u) for g, v, u, _ in valeurs], cfg.anonymiseur), strict=True)
    )
    ids_valeurs = {c: table.valeur(c[2], cle_valeur(c[0], c[1])) for c in valeurs}

    def marquer(texte: str, zs: list[_Zone]) -> dict:
        morceaux, ms, k = [], [], 0
        for z in zs:
            morceaux += [texte[k : z.debut], f"⟦{len(ms)}⟧"]
            k = z.fin
            if z.cle[0] == "NOM":
                ms.append(MarqueNom(genre="NOM", type=z.cle[2], nom=indices[locaux[z.cle]]))
                continue
            g, _, u, p = z.cle
            grandeur, rang, signe = attrs[z.cle]
            ms.append(
                MarqueNombre(
                    genre=g, unite=u, grandeur=grandeur, rang_valeur=rang,
                    valeur_id=ids_valeurs[z.cle], signe=signe, precision=p,
                )
            )  # fmt: skip
        return dict(texte="".join(morceaux) + texte[k:], marques=ms)

    # Relations entre noms.
    declarees = []
    for p, zs in zip(prop_ids, zones[len(historique) + 1 :], strict=True):
        ms = [(z.debut, z.fin, locaux[z.cle]) for z in zs if z.cle[0] == "NOM"]
        declarees += [(a, b, Relation.ALIAS_DECLARE) for a, b in alias_declares(
            lignes[p][2], ms, cfg.noms)]  # fmt: skip
    par_norme: dict[str, list[int]] = {}
    for c, k in locaux.items():
        par_norme.setdefault(c[1], []).append(k)
    for a, b, r in _contraintes(con, conv_id, hypotheses):
        declarees += [(i, j, r) for i in par_norme.get(a, []) for j in par_norme.get(b, [])]
    noms = [
        Nom(n, t, frozenset(surfaces[c]), frozenset(genres[c]))
        for c in cles_noms
        for _, n, t in [c]
    ]
    rel_noms = sorted(
        (indices[a], indices[b], r) for a, b, r in relations_noms(noms, cfg, declarees)
    )

    # Propositions et relations entre propositions.
    local = {p: k for k, p in enumerate(prop_ids)}
    pieces: dict[str, int] = {}
    props = []
    for k, p in enumerate(prop_ids):
        _, piece_id, texte, conf, type_, rang = lignes[p]
        props.append(
            Proposition(
                local=k, prop_id=p, piece=pieces.setdefault(piece_id, len(pieces)),
                type_piece=TypePiece(type_), rang=rang,
                ocr_bas=conf is not None and conf < cfg.anonymiseur.ocr_bas,
                citee_avant=p in citees, **marquer(texte, zones[len(historique) + 1 + k]),
            )
        )  # fmt: skip
    rel_props = set()
    sections: dict[int, list[int]] = {}
    for a, b, t in con.execute(
        f"SELECT src, dst, type FROM arete WHERE src IN ({marques})", list(prop_ids)
    ):
        if t == TypeArete.SECTION_DE:
            sections.setdefault(b, []).append(local[a])
        elif b in local:
            r = _RELATIONS_ARETES[TypeArete(t)]
            a, b = local[a], local[b]
            rel_props.add((min(a, b), max(a, b), r) if r in (Relation.CONFLIT,
                          Relation.DOUBLON_DE) else (a, b, r))  # fmt: skip
    for ks in sections.values():
        rel_props |= {(a, b, Relation.MEME_SECTION) for a in ks for b in ks if a < b}

    return Exemple(
        id=id,
        origine=origine,
        langue="fr",
        question=TexteMarque(**marquer(question.texte, zones[len(historique)])),
        historique=[
            TexteMarque(**marquer(m.texte, zs)) for m, zs in zip(historique, zones, strict=False)
        ],
        propositions=props,
        relations_noms=rel_noms,
        relations_props=sorted(rel_props),
        cible=[],
        justificatives=[],
    )
