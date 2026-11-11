"""Fichiers des sources du corpus de pré-entraînement (SPEC.md §12), dans `racine/brut/<dossier>/`.

Deux temps, comme `jeux.py` :
1. `ccm pretrain telecharger --figer` résout chaque source déclarée (`DECLAREES`) en fichiers
   datés, les télécharge, et écrit leur URL, leur taille et leur SHA-256 dans
   `sources_figees.json` (dans le dépôt, à côté de ce fichier).
2. `ccm pretrain telecharger` ne lit plus que `sources_figees.json` : chaque fichier est
   contrôlé par son empreinte (`jeux.telecharger`, `.part` puis renommé).

Licences : `DATA_LICENSES.md`, à vérifier en ligne avant `--figer`. JORF exclu (vrais noms :
nominations, décorations ; LEGI couvre le droit). Judilibre et LEGI sont déjà sur le disque
(`ccm judilibre`, `ccm jeux`) : ils n'ont rien à télécharger ici.
"""

import json
import re
import urllib.request
from pathlib import Path

from ccm.data.jeux import _sha256
from ccm.data.jeux import telecharger as telecharger_fichiers

FIGEES = Path(__file__).with_name("sources_figees.json")
A_FIGER = None  # révision ou fichier daté : résolu par `--figer`

_WIKI = "https://dumps.wikimedia.org"
_DILA = "https://echanges.dila.gouv.fr/OPENDATA"
_HF = "https://huggingface.co"

# Dumps de Wikipédia : « latest » est résolu en dump daté par le flux RSS du dump.
WIKI = {"wiki_fr": "frwiki", "wiki_en": "enwiki"}
# DILA : dernier stock global `Freemium_<x>_global_*.tar.gz` du dossier (Licence Ouverte 2.0).
DILA = {"dila_cass": "CASS", "dila_inca": "INCA", "dila_jade": "JADE", "dila_capp": "CAPP"}
# Hugging Face : (dépôt, révision, motif des fichiers Parquet, fichiers au plus). La révision
# A_FIGER devient le commit de `main` ; les fichiers sont pris dans l'ordre des noms.
HF = {
    "livres_fr": ("PleIAs/French-PD-Books", A_FIGER, r".*\.parquet", 40),
    "gutenberg_en": ("manu/project_gutenberg", A_FIGER, r"data/en-.*\.parquet", 40),
    "eurlex": ("nlpaueb/multi_eurlex", A_FIGER, r".*\.(jsonl|jsonl\.gz|parquet)", 20),
    "cedh_en": ("ecthr_cases", A_FIGER, r".*\.parquet", 10),
}  # fmt: skip
# Fichiers à URL fixe.
FIXES = {"europarl": ("fr-en.tgz", "https://www.statmt.org/europarl/v7/fr-en.tgz")}


def _lire(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def _wiki(projet: str) -> tuple[str, str]:
    rss = _lire(f"{_WIKI}/{projet}/latest/{projet}-latest-pages-articles.xml.bz2-rss.xml")
    date = re.search(rf"{_WIKI}/{projet}/(\d{{8}})".encode(), rss)
    if date is None:
        raise ValueError(f"date du dump {projet} introuvable")
    d = date[1].decode()
    nom = f"{projet}-{d}-pages-articles.xml.bz2"
    return nom, f"{_WIKI}/{projet}/{d}/{nom}"


def _dila(dossier: str) -> tuple[str, str]:
    page = _lire(f"{_DILA}/{dossier}/").decode("utf-8", "replace")
    stocks = sorted(set(re.findall(r"Freemium_\w+_global_[\d-]+\.tar\.gz", page)))
    if not stocks:
        raise ValueError(f"aucun stock global dans {dossier}")
    return stocks[-1], f"{_DILA}/{dossier}/{stocks[-1]}"


def _hf(depot: str, revision: str | None, motif: str, n: int) -> list[tuple[str, str]]:
    info = json.loads(_lire(f"{_HF}/api/datasets/{depot}/revision/{revision or 'main'}"))
    sha = info["sha"]
    noms = sorted(s["rfilename"] for s in info["siblings"] if re.fullmatch(motif, s["rfilename"]))
    return [
        (n_.replace("/", "__"), f"{_HF}/datasets/{depot}/resolve/{sha}/{n_}") for n_ in noms[:n]
    ]


def resoudre() -> list[tuple[str, str, str]]:
    """(dossier, fichier, URL) de chaque fichier, résolus en ligne (versions datées)."""
    out = [(s, *_wiki(p)) for s, p in WIKI.items()]
    out += [(s, *_dila(d)) for s, d in DILA.items()]
    for s, (depot, rev, motif, n) in HF.items():
        out += [(s, nom, url) for nom, url in _hf(depot, rev, motif, n)]
    out += [(s, nom, url) for s, (nom, url) in FIXES.items()]
    return out


def figer(racine: Path, chemin: Path = FIGEES) -> list[dict]:
    """Résout, télécharge et écrit `sources_figees.json`. Long : plusieurs centaines de Go."""
    fichiers = [(d, nom, url, None) for d, nom, url in resoudre()]
    telecharger_fichiers(racine, fichiers)
    figees = [{"dossier": d, "fichier": nom, "url": url,
               "taille": (racine / "brut" / d / nom).stat().st_size,
               "sha256": _sha256(racine / "brut" / d / nom)}
              for d, nom, url, _ in fichiers]  # fmt: skip
    chemin.write_text(json.dumps(figees, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return figees


def fichiers_figes(chemin: Path = FIGEES) -> list[tuple[str, str, str, str]]:
    if not chemin.exists():
        raise FileNotFoundError(f"{chemin.name} absent : lancer `ccm pretrain telecharger --figer`")
    return [(f["dossier"], f["fichier"], f["url"], f["sha256"])
            for f in json.loads(chemin.read_text(encoding="utf-8"))]  # fmt: skip


def telecharger(racine: Path) -> list[tuple[str, str, int, str]]:
    return telecharger_fichiers(racine, fichiers_figes())
