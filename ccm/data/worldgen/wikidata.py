"""Liste d'exclusion : noms complets de personnes de Wikidata (SPEC.md §12).

Seul module de worldgen qui appelle le réseau ; le générateur lit seulement le
fichier produit (`EXCLUS_WIKIDATA`). On n'envoie que des noms tirés de nos réservoirs.

Deux passes :
1. toutes les paires prénom courant × nom courant des réservoirs ;
2. les « prénom nom » réellement tirés pour le corpus (noms inventés compris),
   jusqu'à point fixe : un nom exclu est tiré de nouveau, le nouveau est vérifié.

Écrit les noms exclus (`EXCLUS_WIKIDATA`) et tous les noms vérifiés
(`VERIFIES_WIKIDATA`) : un test hors ligne contrôle que chaque nom du corpus a été
vérifié. À relancer après tout changement des réservoirs ou de `configs/worldgen.yaml`.

Libellés et alias français d'un humain (Q5), correspondance exacte.
Usage : `uv run python -m ccm.data.worldgen.wikidata`
"""

import json
import time
import urllib.parse
import urllib.request
from collections.abc import Iterable

from ccm.config import WorldgenConfig, load_config
from ccm.data.worldgen.monde import (
    EXCLUS_WIKIDATA,
    VERIFIES_WIKIDATA,
    _reservoirs,
    cle,
    mondes_corpus,
)

AGENT = "ccm-worldgen/0.1 (https://github.com/RaphGonz/Nunda)"
REQUETE = """SELECT DISTINCT ?l WHERE {{
  VALUES ?l {{ {valeurs} }}
  ?p rdfs:label|skos:altLabel ?l ; wdt:P31 wd:Q5 .
}}"""


def _sparql(valeurs: list[str], cfg: WorldgenConfig) -> set[str]:
    litteraux = " ".join(json.dumps(v, ensure_ascii=False) + "@fr" for v in valeurs)
    corps = urllib.parse.urlencode({"query": REQUETE.format(valeurs=litteraux)}).encode()
    requete = urllib.request.Request(
        cfg.wikidata_url,
        data=corps,
        headers={"User-Agent": AGENT, "Accept": "application/sparql-results+json"},
    )
    for essai in range(3):
        try:
            with urllib.request.urlopen(requete, timeout=120) as r:
                return {b["l"]["value"] for b in json.load(r)["results"]["bindings"]}
        except OSError:
            if essai == 2:
                raise
            time.sleep(30 * (essai + 1))
    raise AssertionError


def humains(noms: Iterable[str], cfg: WorldgenConfig) -> set[str]:
    """Noms de `noms` qui sont le libellé ou l'alias français d'un humain."""
    noms = sorted(set(noms))
    trouves: set[str] = set()
    for i in range(0, len(noms), cfg.wikidata_lot):
        trouves |= _sparql(noms[i : i + cfg.wikidata_lot], cfg)
        time.sleep(cfg.wikidata_pause_s)
    return trouves


def paires_courantes() -> set[str]:
    r = _reservoirs()
    return {f"{p} {n}" for p in r["prenoms_m"] + r["prenoms_f"] for n in r["noms"]}


def noms_corpus(cfg: WorldgenConfig, exclus: frozenset[str]) -> set[str]:
    return {f"{p.prenom} {p.nom}" for _, m in mondes_corpus(cfg, exclus) for p in m.personnes}


def construire(cfg: WorldgenConfig) -> tuple[set[str], set[str]]:
    """(noms exclus, noms vérifiés)."""
    verifies = paires_courantes()
    trouves = humains(verifies, cfg)
    while True:
        exclus = frozenset(cle(n) for n in trouves)
        nouveaux = noms_corpus(cfg, exclus) - verifies
        print(f"exclus {len(trouves)}, vérifiés {len(verifies)}, à vérifier {len(nouveaux)}")
        if not nouveaux:
            return trouves, verifies
        trouves |= humains(nouveaux, cfg)
        verifies |= nouveaux


if __name__ == "__main__":
    trouves, verifies = construire(load_config("worldgen"))
    for chemin, noms in [(EXCLUS_WIKIDATA, trouves), (VERIFIES_WIKIDATA, verifies)]:
        lignes = "".join(f"{x}\n" for x in sorted(noms))
        chemin.write_text(lignes, encoding="utf-8", newline="\n")
    print(f"{len(trouves)} noms exclus sur {len(verifies)} vérifiés")
