"""Table de la conversation (SPEC.md §6).

Le dictionnaire norme → indice reste dans le processus de l'anonymiseur ; il n'entre ni
dans le modèle, ni dans la trace. Chaque nom distinct reçoit un indice tiré au hasard,
sans remise, dans le réservoir de K vecteurs de son type. Le tirage est refait à chaque
exemple d'entraînement (une table par exemple), et une fois par conversation à
l'inférence (une table par conversation).

L'indice `nom` d'un exemple est unique pour tous les types : le réservoir du type de rang
r (PER, ORG, LIEU, REF, AUTRE, l'ordre des jetons de §8) occupe les indices r·K à
r·K + K − 1, soit les 5 K vecteurs de slots de la variante A. Les valeurs (nombres et
dates) ont leur propre réservoir de K indices.
"""

import random

from ccm.schema import TypeNom

ORDRE_TYPES = (TypeNom.PER, TypeNom.ORG, TypeNom.LIEU, TypeNom.REF, TypeNom.AUTRE)


class TableConversation:
    def __init__(self, graine: int, k: int):
        self.graine, self.k = graine, k
        self._restants: dict[str, list[int]] = {}
        self._indices: dict[tuple, int] = {}

    def _tirer(self, reservoir: str, cle: tuple) -> int:
        if cle not in self._indices:
            if reservoir not in self._restants:
                ordre = list(range(self.k))
                random.Random(f"{self.graine}:{reservoir}").shuffle(ordre)
                self._restants[reservoir] = ordre[::-1]
            if not self._restants[reservoir]:
                raise ValueError(f"plus de {self.k} {reservoir} distincts dans la conversation")
            self._indices[cle] = self._restants[reservoir].pop()
        return self._indices[cle]

    def nom(self, type_: TypeNom, norme: str) -> int:
        r = ORDRE_TYPES.index(type_)
        return r * self.k + self._tirer(str(type_), ("NOM", type_, norme))

    def valeur(self, unite: str, cle: str) -> int:
        return self._tirer("valeurs", ("VAL", unite, cle))
