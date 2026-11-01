"""Échantillon de décisions de Judilibre, par l'API de PISTE (SPEC.md §12).

Pas de dump : `/scan` par mois et par juridiction, avec une part égale par mois (échantillon
réparti dans le temps ; dans un mois, les premières décisions par date). Chaque fenêtre donne
un fichier `racine/brut/judilibre/<juridiction>/<AAAA-MM>.jsonl.gz`, écrit d'un coup : un
fichier présent n'est pas redemandé, relancer reprend après un arrêt. Les quotas (CGU PISTE :
à ne pas contourner) sont respectés par une pause entre deux appels ; un refus 429 ou une
panne fait attendre puis, s'il persiste, arrête proprement. CGU de Judilibre, art. V : la
juridiction, la formation, le siège et la date restent attachés à chaque décision (en-tête) ;
art. VI : aucune indexation des magistrats ni des greffiers.

La clé (`KeyId`) vient de l'environnement `PISTE_KEY_ID`, ou du fichier `racine/piste-cle.txt` :
jamais dans le dépôt.
"""

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

from ccm.config import DonneesConfig, JudilibreConfig
from ccm.data.droit import Texte, net
from ccm.schema import TypePiece


class ArretJudilibre(Exception):
    """L'API refuse ou ne répond plus : à relancer plus tard, ce qui est écrit reste."""


def lire_cle(racine: Path) -> str | None:
    cle = os.environ.get("PISTE_KEY_ID")
    fichier = racine / "piste-cle.txt"
    if not cle and fichier.exists():  # les lignes en « # » sont le mode d'emploi du fichier
        lignes = fichier.read_text(encoding="utf-8-sig").splitlines()
        cle = next((x for x in lignes if x.strip() and not x.lstrip().startswith("#")), None)
    return cle.strip() if cle and cle.strip() else None


def _mois(debut: str, fin: str) -> Iterator[str]:
    a, m = map(int, debut.split("-"))
    while f"{a:04d}-{m:02d}" <= fin:
        yield f"{a:04d}-{m:02d}"
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def fenetres(cfg: JudilibreConfig) -> list[tuple[str, str]]:
    return [(jur, m) for jur, d in cfg.juridictions.items() for m in _mois(d, cfg.fin)]


def _lire(url: str, cle: str) -> dict:
    req = urllib.request.Request(url, headers={"KeyId": cle, "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _appeler(url: str, cle: str, cfg: JudilibreConfig, lire, dormir) -> dict:
    """Une réponse ; attend entre les essais (`Retry-After` s'il est donné). Le message
    d'erreur ne contient jamais la clé."""
    raison = ""
    for essai in range(cfg.essais):
        dormir(cfg.pause_s)
        try:
            return lire(url, cle)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ArretJudilibre(f"HTTP {e.code} : clé ou CGU de Judilibre à valider") from None
            if e.code != 429 and e.code < 500:
                raise ArretJudilibre(f"HTTP {e.code} sur {url}") from None
            attente = e.headers.get("Retry-After") if e.headers else None
            raison = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            attente, raison = None, type(e).__name__
        try:
            duree = float(attente)
        except (TypeError, ValueError):
            duree = cfg.attente_s * 2**essai
        print(f"{raison} : nouvel essai dans {duree:.0f} s", flush=True)
        dormir(duree)
    raise ArretJudilibre(f"{raison} après {cfg.essais} essais")


def _fenetre(jur: str, mois: str, part: int, cle: str, cfg: JudilibreConfig, lire, dormir
             ) -> list[dict]:  # fmt: skip
    a, m = map(int, mois.split("-"))
    suivant = f"{a + 1:04d}-01-01" if m == 12 else f"{a:04d}-{m + 1:02d}-01"
    decisions: list[dict] = []
    apres = None
    while len(decisions) < part:
        p = {
            "jurisdiction": jur,
            "date_type": "creation",  # sinon la date de mise à jour
            "date_start": f"{mois}-01",
            "date_end": suivant,
            "order": "asc",
            "batch_size": min(cfg.lot, part - len(decisions)),
        }
        if apres:
            p["search_after"] = apres
        rep = _appeler(f"{cfg.url}/scan?{urllib.parse.urlencode(p)}", cle, cfg, lire, dormir)
        # Si `date_end` est inclus par l'API, le premier du mois suivant reste à sa fenêtre.
        lus = [d for d in rep.get("results") or [] if d.get("decision_date", "")[:7] == mois]
        decisions += lus[: part - len(decisions)]
        suite = urllib.parse.parse_qs(urllib.parse.urlsplit(rep.get("next_batch") or "").query)
        apres = suite.get("search_after", [None])[0]
        if not apres or not rep.get("results"):
            break
    return decisions


def telecharger(
    racine: Path,
    cfg: DonneesConfig,
    cle: str,
    lire: Callable[[str, str], dict] = _lire,
    dormir: Callable[[float], None] = time.sleep,
) -> dict:
    """Télécharge les fenêtres manquantes ; rend le bilan des fenêtres et des décisions."""
    j = cfg.judilibre
    fs = fenetres(j)
    part = j.total // len(fs)
    decisions = 0
    for jur, mois in fs:
        cible = racine / "brut" / "judilibre" / jur / f"{mois}.jsonl.gz"
        if not cible.exists():
            lus = _fenetre(jur, mois, part, cle, j, lire, dormir)
            cible.parent.mkdir(parents=True, exist_ok=True)
            partiel = cible.with_suffix(".part")
            with gzip.open(partiel, "wt", encoding="utf-8", newline="\n") as f:
                f.writelines(json.dumps(d, ensure_ascii=False) + "\n" for d in lus)
            partiel.replace(cible)
            print(f"{jur} {mois} : {len(lus)} décisions", flush=True)
        with gzip.open(cible, "rt", encoding="utf-8") as f:
            decisions += sum(1 for _ in f)
    return {"fenetres": len(fs), "decisions": decisions, "part_par_fenetre": part}


def _tete(d: dict) -> str:
    champs = (d.get("jurisdiction"), d.get("chamber"), d.get("formation"), d.get("location"),
              d.get("number"), d.get("decision_date"))  # fmt: skip
    return "Décision : " + ", ".join(str(c) for c in champs if c)


def textes(racine: Path) -> Iterator[Texte]:
    """Les décisions téléchargées, dans l'ordre des fichiers, en paragraphes."""
    for fichier in sorted((racine / "brut" / "judilibre").glob("*/*.jsonl.gz")):
        with gzip.open(fichier, "rt", encoding="utf-8") as f:
            for ligne in f:
                d = json.loads(ligne)
                pars = [net(p) for p in (d.get("text") or "").replace("\r", "").split("\n\n")]
                pars = tuple((p, False) for p in pars if p)
                if not pars:
                    continue
                sha = hashlib.sha256(f"{d['id']}\n{d['text']}".encode()).hexdigest()
                yield Texte(f"judilibre-{d['id']}", f"judilibre:{d['id']}", sha,
                            TypePiece.AUTRE, _tete(d), pars)  # fmt: skip
