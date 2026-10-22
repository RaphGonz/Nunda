"""Entrée du modèle (SPEC.md §8) : tables de relations NN et PP d'un exemple.

Les noms reçoivent un numéro local 1 à N par première apparition (historique, question,
propositions), les valeurs aussi. NN[i, j] est le masque de bits des relations 1 à 14 du
nom i vers le nom j (bit id − 1) ; PP de même pour les relations 16 à 24 entre
propositions. La ligne et la colonne 0 sont vides. Une relation orientée (a, b, R) met
son premier identifiant en NN[a, b] et le second en NN[b, a].
"""

import numpy as np

from ccm.schema import RELATION_IDS, Exemple, Relation


def ordre_apparition(ex: Exemple) -> tuple[dict[int, int], dict[int, int]]:
    """Indice `nom` → numéro local, `valeur_id` → numéro local (1, 2, …)."""
    noms: dict[int, int] = {}
    vals: dict[int, int] = {}
    for t in (*ex.historique, ex.question, *ex.propositions):
        for m in t.marques:
            if m.genre == "NOM":
                noms.setdefault(m.nom, len(noms) + 1)
            else:
                vals.setdefault(m.valeur_id, len(vals) + 1)
    return noms, vals


def _bit(r: Relation, sens: int) -> int:
    return 1 << (RELATION_IDS[r][sens] - 1)


def _poser(t: np.ndarray, a: int, b: int, r: Relation) -> None:
    t[a, b] |= _bit(r, 0)
    t[b, a] |= _bit(r, -1)


def tables_relations(ex: Exemple) -> tuple[np.ndarray, np.ndarray]:
    noms, _ = ordre_apparition(ex)
    nn = np.zeros((len(noms) + 1, len(noms) + 1), dtype=np.int64)
    for k in noms.values():
        nn[k, k] |= _bit(Relation.MEME_CHAINE, 0)
    for a, b, r in ex.relations_noms:
        _poser(nn, noms[a], noms[b], r)

    p = len(ex.propositions)
    pp = np.zeros((p + 1, p + 1), dtype=np.int64)
    for x in ex.propositions:
        pp[x.local + 1, x.local + 1] |= _bit(Relation.MEME_PROPOSITION, 0)
        for y in ex.propositions:
            if x.piece == y.piece:
                pp[x.local + 1, y.local + 1] |= _bit(Relation.MEME_PIECE, 0)
    for a, b, r in ex.relations_props:
        _poser(pp, a + 1, b + 1, r)
    return nn, pp
