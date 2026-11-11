"""Téléchargement des jeux publics (SPEC.md §12) dans `racine/brut/<jeu>/`.

Versions figées, empreintes SHA-256 contrôlées ; licences dans `DATA_LICENSES.md`. Un jeu
n'entre dans `FICHIERS` qu'une fois sa licence lue et claire. Absent : FQuAD (accès refusé,
HTTP 401). PIAF : CC BY-SA retenue par Raphael (`JOURNAL.md`, 2026-10-31).

    uv run ccm jeux
"""

import hashlib
import urllib.request
from pathlib import Path

_HOTPOT = "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/1908d6afbbead072334abe2965f91bd2709910ab/distractor"
_PIAF = "https://static.data.gouv.fr/resources/piaf-le-dataset-francophone-de-questions-reponses/20210323-174441"
_SQUAD = "https://rajpurkar.github.io/SQuAD-explorer/dataset"
_FINQA = "https://raw.githubusercontent.com/czyssrs/FinQA/main"
_LEGI = "https://echanges.dila.gouv.fr/OPENDATA/LEGI"
_TAB = "https://raw.githubusercontent.com/NorskRegnesentral/text-anonymization-benchmark/master"

# (jeu, fichier local, URL, SHA-256)
FICHIERS = [
    ("hotpot", "train-00000-of-00002.parquet", f"{_HOTPOT}/train-00000-of-00002.parquet",
     "76d3bb3048a7cc73c1958107c0c5872a00d7e7d00c105b81e92f6769e7822e68"),
    ("hotpot", "train-00001-of-00002.parquet", f"{_HOTPOT}/train-00001-of-00002.parquet",
     "713661628434fbb19fff7392e2e321e4ed107e3c7c7784d0690946e5f722763f"),
    ("hotpot", "validation-00000-of-00001.parquet", f"{_HOTPOT}/validation-00000-of-00001.parquet",
     "c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6"),
    ("piaf", "piaf-v1.2.json", f"{_PIAF}/piaf-v1.2.json",
     "6f2734336d64e4a363bd6bbcc790a8ff993af51586f73a57f1d15a34d8440bf2"),
    ("squad", "train-v2.0.json", f"{_SQUAD}/train-v2.0.json",
     "68dcfbb971bd3e96d5b46c7177b16c1a4e7d4bdef19fb204502738552dede002"),
    ("squad", "dev-v2.0.json", f"{_SQUAD}/dev-v2.0.json",
     "80a5225e94905956a6446d296ca1093975c4d3b3260f1d6c8f68bc2ab77182d8"),
    ("finqa", "train.json", f"{_FINQA}/dataset/train.json",
     "49f237eb9779b569473b26b08048867d04635a7cc39ad6a7a5664c55bb428db6"),
    ("finqa", "dev.json", f"{_FINQA}/dataset/dev.json",
     "a847fb7e0d61a3125a1e2909852df6b89f1ee64d2c5ff1bf689e332214deee51"),
    ("finqa", "test.json", f"{_FINQA}/dataset/test.json",
     "831dbfb2e785dbc227f895ce3f24046433467aec67b09db2bd6ac7692a8a30dc"),
    ("finqa", "LICENSE", f"{_FINQA}/LICENSE",
     "92c0e67bd762c15c07ba60de09558338315a8ebf99aac4f51f487179809ac087"),
    ("legi", "Freemium_legi_global_20250713-140000.tar.gz",
     f"{_LEGI}/Freemium_legi_global_20250713-140000.tar.gz",
     "f862b4a2238e11ec3c48ec70f3b1c68bac0bb1985907841666b98608653d4eca"),
    ("tab", "echr_train.json", f"{_TAB}/echr_train.json",
     "4aba41f8ac305ff9e93dd6f0bbc16756e57e9ace396c827931fab70e18d8c6a6"),
    ("tab", "echr_dev.json", f"{_TAB}/echr_dev.json",
     "8c3c7306f46b8d54debeb38ae11d8b0b8bcf4bdccbc3b6f13c12ad7be16893ec"),
    ("tab", "echr_test.json", f"{_TAB}/echr_test.json",
     "cd0f0f15f84a8739654c7cf30c6be8ce27b051ef73974d39d792a0cb8c846379"),
    ("tab", "LICENSE.txt", f"{_TAB}/LICENSE.txt",
     "9569b31acf50e1cb3f38f47220f2c3a42f533e07e72fe2d18c2871e89098a8c7"),
]  # fmt: skip


def _sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        while bloc := f.read(1 << 20):
            h.update(bloc)
    return h.hexdigest()


def telecharger(racine: Path, fichiers: list | None = None) -> list[tuple[str, str, int, str]]:
    """Télécharge ce qui manque (`fichiers` : `FICHIERS` par défaut) ; rend (jeu, fichier,
    taille, SHA-256) de chaque fichier."""
    bilan = []
    for jeu, nom, url, empreinte in FICHIERS if fichiers is None else fichiers:
        cible = racine / "brut" / jeu / nom
        if not (cible.exists() and (empreinte is None or _sha256(cible) == empreinte)):
            cible.parent.mkdir(parents=True, exist_ok=True)
            partiel = cible.with_suffix(cible.suffix + ".part")
            with urllib.request.urlopen(url, timeout=120) as r, partiel.open("wb") as f:
                annonce = r.headers.get("Content-Length")
                while bloc := r.read(1 << 20):
                    f.write(bloc)
            if annonce is not None and partiel.stat().st_size != int(annonce):
                partiel.unlink()
                raise ValueError(f"taille inattendue : {url}")
            if empreinte is not None and _sha256(partiel) != empreinte:
                partiel.unlink()
                raise ValueError(f"empreinte inattendue : {url}")
            partiel.replace(cible)
        bilan.append((jeu, nom, cible.stat().st_size, _sha256(cible)))
    return bilan
