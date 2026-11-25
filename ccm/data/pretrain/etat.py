"""État d'une étape : paquets finis, écrits d'un coup (`.part` puis renommé).

`etat.json` garde, pour chaque paquet fini, son bilan ; `complet` est vrai quand l'étape a
écrit tous ses paquets. Un paquet est fini s'il est dans `etat.json` et sur le disque : un
arrêt pendant l'écriture laisse un `.part`, effacé et refait à la relance.
"""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def nom_paquet(n: int, prefixe: str = "paquet") -> str:
    return f"{prefixe}-{n:05d}.parquet"


def ecrire_atomique(chemin: Path, octets: bytes) -> None:
    partiel = chemin.with_name(chemin.name + ".part")
    partiel.write_bytes(octets)
    partiel.replace(chemin)


def ecrire_table(colonnes: dict[str, list], schema: pa.Schema, chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pydict(colonnes, schema=schema)
    partiel = chemin.with_name(chemin.name + ".part")
    pq.write_table(table, partiel, compression="zstd")
    partiel.replace(chemin)


def lire_lignes(chemin: Path) -> Iterator[dict]:
    """Lignes d'un paquet, par lots (jamais tout le fichier en dictionnaires)."""
    for lot in pq.ParquetFile(chemin).iter_batches(batch_size=1000):
        yield from lot.to_pylist()


def tirage(graine: int, quoi: str, id: str) -> float:
    """Nombre de [0, 1) fixé par la graine, l'usage et l'id : même tirage à chaque relance."""
    h = hashlib.sha1(f"{graine}:{quoi}:{id}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


class Etape:
    def __init__(self, dossier: Path):
        self.dossier = dossier
        dossier.mkdir(parents=True, exist_ok=True)
        self.chemin = dossier / "etat.json"
        lu = json.loads(self.chemin.read_text(encoding="utf-8")) if self.chemin.exists() else {}
        self.etat = {"paquets": {}, "complet": False} | lu
        for p in dossier.glob("*.part"):
            p.unlink()

    def chemin_paquet(self, n: int, prefixe: str = "paquet") -> Path:
        return self.dossier / nom_paquet(n, prefixe)

    def fini(self, n: int) -> bool:
        return str(n) in self.etat["paquets"] and self.chemin_paquet(n).exists()

    def bilan(self, n: int) -> dict:
        return self.etat["paquets"][str(n)]

    def finir(self, n: int, bilan: dict) -> None:
        self.etat["paquets"][str(n)] = bilan
        self._ecrire()

    def completer(self, **en_plus) -> None:
        self.etat.update(complet=True, **en_plus)
        self._ecrire()

    @property
    def complet(self) -> bool:
        return self.etat["complet"]

    def paquets(self) -> list[int]:
        return sorted(int(n) for n in self.etat["paquets"])

    def _ecrire(self) -> None:
        texte = json.dumps(self.etat, indent=1, ensure_ascii=False, sort_keys=True)
        ecrire_atomique(self.chemin, texte.encode("utf-8"))
