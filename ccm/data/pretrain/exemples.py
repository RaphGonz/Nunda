"""Exemples de pré-entraînement de B (SPEC.md §8, §13) depuis les fenêtres de `final/`.

`encoder` : texte BPE (marqueurs ⟦k⟧ → jetons de slot), [BOS] en tête, coupé à `t_max`.
Le k-ième jeton de slot de la séquence porte la k-ième marque : `name_idx` = nom + 1,
`val_idx` = valeur + 1, `num_attr` comme `encode.Vocabulaire.attributs`. `prop_idx` : dans
une fenêtre [P], numéro de la proposition de [P] à [/P] compris. NN depuis la colonne `nn`,
PP depuis `n_props` (`remplacer`).

`tirer` : mode causal ou préfixe, à parts égales (§13), par graine sur (passage, id).
- Causal : tout en segment 2 ; la position t − 1 prédit le jeton t.
- Préfixe : coupe après une fin de phrase entre 25 % et 75 % de la longueur ; préfixe en
  segment 1, suite en segment 2. 15 % des jetons du préfixe (ni [BOS] ni le dernier, qui
  prédit le premier jeton de la suite) deviennent [MASK] et sont prédits à leur place ; un
  slot masqué perd `name_idx`, `val_idx` et `num_attr` (§13).
Pour chaque slot prédit : un pas de pointeur (position qui prédit, position du slot).
"""

import json
import random
from dataclasses import dataclass

import numpy as np

from ccm.anonymize.encode import Vocabulaire
from ccm.data.pretrain.bpe import SLOTS
from ccm.data.pretrain.remplacer import tables_nn, tables_pp
from ccm.schema import MarqueNombre

FAM_NOM, FAM_VAL = 1, 2


class Jetons:
    """Identifiants utiles du BPE de B, et les jetons qui finissent une phrase."""

    def __init__(self, tok):
        self.tok = tok
        i = tok.token_to_id
        self.bos, self.mask, self.nouveau = i("[BOS]"), i("[MASK]"), i("[NOUVEAU]")
        self.p, self.fp = i("[P]"), i("[/P]")
        self.famille = np.zeros(tok.get_vocab_size(), dtype=np.int8)
        for t, s in SLOTS.items():
            self.famille[i(s)] = FAM_VAL if t in ("NUM", "DATE") else FAM_NOM
        fins = [tok.decode([k]).rstrip(" ").endswith((".", "!", "?", "\n"))
                for k in range(tok.get_vocab_size())]  # fmt: skip
        self.fin_phrase = np.array(fins)
        self.fin_phrase[self.fp] = True


@dataclass
class Fenetre:
    ids: np.ndarray  # T
    prop_idx: np.ndarray
    name_idx: np.ndarray
    val_idx: np.ndarray
    num_attr: np.ndarray  # T × 4
    NN: np.ndarray
    PP: np.ndarray


def encoder(f: dict, j: Jetons, voc: Vocabulaire, t_max: int) -> Fenetre:
    from ccm.data.pretrain.bpe import texte_bpe

    marques = json.loads(f["marques"])
    ids = np.array([j.bos, *j.tok.encode(texte_bpe(f["texte"], marques)).ids][:t_max])
    T = len(ids)
    nom, val = np.zeros(T, np.int64), np.zeros(T, np.int64)
    attr = np.zeros((T, 4), np.int64)
    for k, pos in enumerate(np.flatnonzero(j.famille[ids])):
        m = marques[k]
        if m["genre"] == "NOM":
            nom[pos] = m["nom"] + 1
        else:
            val[pos] = m["valeur_id"] + 1
            attr[pos] = voc.attributs(MarqueNombre(**m))
    prop = np.zeros(T, np.int64)
    if f["a_p"]:
        debut = np.cumsum(ids == j.p)
        fin = np.cumsum(ids == j.fp) - (ids == j.fp)  # [/P] compte dans sa proposition
        prop = np.where(debut > fin, debut, 0)
    nn_ = tables_nn(f["noms"], json.loads(f["nn"]))
    pp = tables_pp(f["n_props"]) if f["a_p"] else np.zeros((1, 1), np.int64)
    return Fenetre(ids, prop, nom, val, attr, nn_, pp)


@dataclass
class ExempleB:
    """Entrée (`Fenetre` modifiée), cibles des mots (−100 : rien), pas de pointeur."""

    ids: np.ndarray
    segment: np.ndarray
    prop_idx: np.ndarray
    name_idx: np.ndarray
    val_idx: np.ndarray
    num_attr: np.ndarray
    NN: np.ndarray
    PP: np.ndarray
    cible: np.ndarray  # T : jeton prédit à chaque position
    famille: np.ndarray  # T : famille du slot d'origine (0, FAM_NOM, FAM_VAL)
    origine: np.ndarray  # T : name_idx ou val_idx d'origine
    masque: np.ndarray  # T : jeton remplacé par [MASK]
    pas: np.ndarray  # K × 2 : (position qui prédit, position du slot)
    attr_cible: np.ndarray  # K × 2 : unité, grandeur (0 pour un nom)


def _coupe(ids: np.ndarray, j: Jetons, bornes: tuple[float, float], rng: random.Random) -> int:
    T = len(ids)
    lo, hi = int(bornes[0] * T), int(bornes[1] * T)
    fins = [i + 1 for i in np.flatnonzero(j.fin_phrase[ids[:-1]]) if lo <= i + 1 <= hi]
    return rng.choice(fins) if fins else max(T // 2, 1)


def tirer(w: Fenetre, j: Jetons, prefixe: bool, part_masque: float,
          bornes: tuple[float, float], rng: random.Random) -> ExempleB:  # fmt: skip
    T = len(w.ids)
    fam = j.famille[w.ids].astype(np.int64)
    origine = np.where(fam == FAM_NOM, w.name_idx, w.val_idx)
    ids, nom, val, attr = w.ids.copy(), w.name_idx.copy(), w.val_idx.copy(), w.num_attr.copy()
    seg = np.full(T, 2, np.int64)
    cible = np.full(T, -100, np.int64)
    masque = np.zeros(T, bool)
    debut = 1
    if prefixe and T >= 4:
        c = _coupe(w.ids, j, bornes, rng)
        seg[:c] = 1
        candidats = list(range(1, c - 1))
        for i in rng.sample(candidats, round(part_masque * len(candidats))):
            masque[i] = True
        ids[masque], nom[masque], val[masque], attr[masque] = j.mask, 0, 0, 0
        cible[masque] = w.ids[masque]
        debut = c
    cible[debut - 1 : T - 1] = w.ids[debut:]
    pas = [(i, i) for i in np.flatnonzero(masque & (fam > 0))]
    pas += [(i - 1, i) for i in range(debut, T) if fam[i]]
    pas_ = np.array(pas, np.int64).reshape(-1, 2)
    s = pas_[:, 1]
    attr_c = np.where((fam[s] == FAM_VAL)[:, None], w.num_attr[s][:, :2], 0)
    return ExempleB(ids, seg, w.prop_idx, nom, val, attr, w.NN, w.PP, cible, fam, origine,
                    masque, pas_, attr_c)  # fmt: skip
