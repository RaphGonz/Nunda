"""Remplacement des noms et des nombres d'une fenêtre, relations (SPEC.md §6, §8, §12).

Une fenêtre est un exemple : ses noms reçoivent un indice local 0, 1, … par première
apparition (même norme et même type, `norme`), ses valeurs aussi. Chaque mention devient un
marqueur ⟦k⟧ et une marque (`MarqueNom`, `MarqueNombre` avec ses attributs, `units.attributs`).
**Aucune chaîne de nom n'est écrite** : les surfaces ne servent qu'aux relations, en mémoire.

Relations entre noms : 2 à 11 (`relations_noms`, `alias_declares`), en masques de bits comme
`encode.tables_relations` (`_bit`) : `nn` liste les cases non nulles (a, b, bits) hors de la
diagonale, qui porte toujours MEME_CHAINE. Dans un document [P], chaque phrase est entourée
de [P] … [/P] ; entre propositions : 16 MEME_PROPOSITION (diagonale), 17/18 SUIVANTE (phrases
voisines), 23 MEME_PIECE (toutes les paires : une fenêtre vient d'un seul document, une
pièce). La table PP se déduit du seul nombre de propositions (`tables_pp`).
"""

import json

import numpy as np

from ccm.anonymize.encode import _bit, _poser
from ccm.anonymize.exemple import _zones
from ccm.anonymize.relations import Nom, alias_declares, genre_titre, relations_noms
from ccm.anonymize.units import attributs, cle_valeur
from ccm.config import IngestConfig
from ccm.data.publics import _nombres
from ccm.ner.detectors import Zone
from ccm.schema import MarqueNom, MarqueNombre, Relation, TexteMarque


def tables_pp(n: int) -> np.ndarray:
    """Table PP (1 à n, ligne et colonne 0 vides, comme `encode`) d'une fenêtre [P]."""
    pp = np.zeros((n + 1, n + 1), dtype=np.int64)
    pp[1:, 1:] |= _bit(Relation.MEME_PIECE, 0)
    for i in range(1, n + 1):
        pp[i, i] |= _bit(Relation.MEME_PROPOSITION, 0)
        if i < n:
            _poser(pp, i, i + 1, Relation.SUIVANTE)
    return pp


def tables_nn(n: int, nn: list[list[int]]) -> np.ndarray:
    """Table NN (1 à n, comme `encode`) depuis la colonne `nn` (indices 0 à n − 1)."""
    t = np.zeros((n + 1, n + 1), dtype=np.int64)
    for k in range(1, n + 1):
        t[k, k] |= _bit(Relation.MEME_CHAINE, 0)
    for a, b, bits in nn:
        t[a + 1, b + 1] |= bits
    return t


def marquer_fenetre(phrases: list[str], separateurs: list[str], zones: list[list[Zone]],
                    langue: str, a_p: bool, cfg: IngestConfig) -> dict:  # fmt: skip
    """Texte marqué, marques, relations entre noms, nombre de propositions et fins des phrases
    d'une fenêtre.
    `separateurs[i]` : blanc écrit avant la phrase i (rien avant la première)."""
    par_phrase = []
    for t, zs in zip(phrases, zones, strict=True):
        exclus = [(z.debut, z.fin) for z in zs]
        nbs = [(n.debut, n.fin, n.genre, n.valeur, n.unite, n.precision)
               for n in _nombres(t, exclus, langue, cfg)]  # fmt: skip
        par_phrase.append(_zones(t, [(z.debut, z.fin, z.type) for z in zs], nbs, cfg))

    locaux: dict[tuple, int] = {}
    surfaces: dict[tuple, set] = {}
    genres: dict[tuple, set] = {}
    valeurs: dict[tuple, int] = {}
    for t, zs in zip(phrases, par_phrase, strict=True):
        for z in zs:
            if z.cle[0] == "NOM":
                locaux.setdefault(z.cle, len(locaux))
                surfaces.setdefault(z.cle, set()).add(t[z.debut : z.fin])
                g = genre_titre(t, z.debut, cfg.noms)
                genres.setdefault(z.cle, set()).update([g] if g else [])
            else:
                valeurs.setdefault(z.cle, len(valeurs))
    attrs = dict(zip(valeurs, attributs([(g, v, u) for g, v, u, _ in valeurs], cfg.anonymiseur),
                     strict=True))  # fmt: skip
    par_cle: dict[tuple, int] = {}  # même valeur, même unité : même identifiant
    ids_valeurs = {c: par_cle.setdefault((c[2], cle_valeur(c[0], c[1])), len(par_cle))
                   for c in valeurs}  # fmt: skip

    morceaux, marques, declarees, bornes = [], [], [], []
    for i, (t, zs) in enumerate(zip(phrases, par_phrase, strict=True)):
        if i:
            morceaux.append(separateurs[i])
        if a_p:
            morceaux.append("[P] ")
        k = 0
        for z in zs:
            morceaux += [t[k : z.debut], f"⟦{len(marques)}⟧"]
            k = z.fin
            if z.cle[0] == "NOM":
                marques.append(MarqueNom(genre="NOM", type=z.cle[2], nom=locaux[z.cle]))
                continue
            g, _, u, p = z.cle
            grandeur, rang, signe = attrs[z.cle]
            marques.append(MarqueNombre(
                genre=g, unite=u, grandeur=grandeur, rang_valeur=rang,
                valeur_id=ids_valeurs[z.cle], signe=signe, precision=p,
            ))  # fmt: skip
        morceaux.append(t[k:])
        if a_p:
            morceaux.append(" [/P]")
        bornes.append(sum(map(len, morceaux)))
        ms = [(z.debut, z.fin, locaux[z.cle]) for z in zs if z.cle[0] == "NOM"]
        declarees += [(a, b, Relation.ALIAS_DECLARE) for a, b in alias_declares(t, ms, cfg.noms)]

    noms = [Nom(c[1], c[2], frozenset(surfaces[c]), frozenset(genres[c])) for c in locaux]
    nn = np.zeros((len(noms), len(noms)), dtype=np.int64)
    for a, b, r in relations_noms(noms, cfg, declarees):
        _poser(nn, a, b, r)
    texte = TexteMarque(texte="".join(morceaux), marques=marques)  # contrôle des marqueurs
    return {
        "texte": texte.texte,
        "marques": json.dumps([m.model_dump(mode="json") for m in marques], ensure_ascii=False),
        "noms": len(noms),
        "nn": json.dumps(
            [[int(a), int(b), int(nn[a, b])] for a, b in zip(*np.nonzero(nn), strict=True)]
        ),
        "n_props": len(phrases) if a_p else 0,
        "bornes": bornes,  # fin de chaque phrase dans le texte marqué (canaris forcés)
    }
