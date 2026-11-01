"""Échantillon de décisions de Judilibre, par l'API de PISTE (SPEC.md §12).

Pas de dump : `/scan` jour par jour et par juridiction, avec une part égale par mois (échantillon
réparti dans le temps ; dans un jour, les premières décisions rendues par l'API). Chaque mois donne
un fichier `racine/brut/judilibre/<juridiction>/<AAAA-MM>.jsonl.gz`, écrit d'un coup : un
fichier présent n'est pas redemandé, relancer reprend après un arrêt. Les quotas (CGU PISTE :
à ne pas contourner) sont respectés par une pause entre deux appels ; un refus 429 ou une
panne fait attendre puis, s'il persiste, arrête proprement. CGU de Judilibre, art. V : la
juridiction, la formation, le siège et la date restent attachés à chaque décision (en-tête) ;
art. VI : aucune indexation des magistrats ni des greffiers.

Les identifiants OAuth viennent de l'environnement (`PISTE_CLIENT_ID`, `PISTE_CLIENT_SECRET`) ou
du fichier `racine/piste-identifiants.txt` : jamais dans le dépôt.
"""

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from calendar import monthrange
from collections.abc import Callable, Iterator
from math import ceil
from pathlib import Path

from ccm.config import DonneesConfig, JudilibreConfig
from ccm.data.droit import Texte, net
from ccm.schema import TypePiece

FICHIER_IDENTIFIANTS = "piste-identifiants.txt"


class ArretJudilibre(Exception):
    """L'API refuse ou ne répond plus : à relancer plus tard, ce qui est écrit reste."""


def lire_identifiants(racine: Path) -> tuple[str, str] | None:
    """(client_id, client_secret) : environnement, sinon fichier « nom = valeur » ; None si
    l'un manque. Les lignes en « # » sont le mode d'emploi du fichier."""
    vus = {
        "client_id": os.environ.get("PISTE_CLIENT_ID"),
        "client_secret": os.environ.get("PISTE_CLIENT_SECRET"),
    }
    fichier = racine / FICHIER_IDENTIFIANTS
    if fichier.exists():
        for ligne in fichier.read_text(encoding="utf-8-sig").splitlines():
            nom, _, valeur = ligne.partition("=")
            if not ligne.lstrip().startswith("#") and nom.strip() in vus:
                vus[nom.strip()] = vus[nom.strip()] or valeur.strip().strip("\"'<>")
    return (vus["client_id"], vus["client_secret"]) if all(vus.values()) else None


class Jetons:
    """Jeton OAuth 2.0 de PISTE (CGU de Judilibre, art. XI C), redemandé avant sa fin. Une
    erreur ne cite jamais les identifiants."""

    def __init__(self, url: str, client_id: str, secret: str, ouvrir=urllib.request.urlopen):
        self.url, self.id, self.secret, self.ouvrir = url, client_id, secret, ouvrir
        self.jeton, self.fin = "", 0.0

    def __call__(self) -> str:
        if time.monotonic() >= self.fin:
            corps = urllib.parse.urlencode({
                "grant_type": "client_credentials", "client_id": self.id,
                "client_secret": self.secret, "scope": "openid",
            }).encode()  # fmt: skip
            try:
                with self.ouvrir(urllib.request.Request(self.url, corps), timeout=60) as r:
                    d = json.load(r)
            except urllib.error.HTTPError as e:
                raise ArretJudilibre(f"HTTP {e.code} sur le jeton : identifiants ?") from None
            self.jeton = d["access_token"]
            self.fin = time.monotonic() + float(d.get("expires_in", 3600)) - 60
        return self.jeton


def _mois(debut: str, fin: str) -> Iterator[str]:
    a, m = map(int, debut.split("-"))
    while f"{a:04d}-{m:02d}" <= fin:
        yield f"{a:04d}-{m:02d}"
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def fenetres(cfg: JudilibreConfig) -> list[tuple[str, str]]:
    return [(jur, m) for jur, d in cfg.juridictions.items() for m in _mois(d, cfg.fin)]


def _lire(url: str, cle: Callable[[], str]) -> dict:
    entetes = {"Authorization": f"Bearer {cle()}", "accept": "application/json"}
    req = urllib.request.Request(url, headers=entetes)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _appeler(url: str, cle, cfg: JudilibreConfig, lire, dormir) -> dict:
    """Une réponse ; attend entre les essais (`Retry-After` s'il est donné)."""
    raison = ""
    for essai in range(cfg.essais):
        dormir(cfg.pause_s)
        try:
            return lire(url, cle)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ArretJudilibre(
                    f"HTTP {e.code} : API ou CGU de Judilibre à valider sur PISTE"
                ) from None
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


def _fenetre(jur: str, mois: str, part: int, cle, cfg: JudilibreConfig, lire, dormir) -> list[dict]:
    """Un appel par jour : l'API trie par date, un appel par mois ne verrait que ses premiers
    jours. Chaque jour demande sa part de ce qui reste : un jour vide reporte sur les suivants."""
    a, m = map(int, mois.split("-"))
    jours = monthrange(a, m)[1]
    decisions: list[dict] = []
    for j in range(1, jours + 1):
        besoin = min(cfg.lot, ceil((part - len(decisions)) / (jours - j + 1)))
        if besoin <= 0:
            break
        date = f"{mois}-{j:02d}"
        p = {
            "jurisdiction": jur,
            "date_type": "creation",  # sinon la date de mise à jour
            "date_start": date,
            "date_end": date,
            "batch_size": besoin,
        }
        rep = _appeler(f"{cfg.url}/scan?{urllib.parse.urlencode(p)}", cle, cfg, lire, dormir)
        decisions += (rep.get("results") or [])[:besoin]
    return decisions


def telecharger(
    racine: Path,
    cfg: DonneesConfig,
    cle,
    lire: Callable[..., dict] = _lire,
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


_JURIDICTIONS = {"cc": "Cour de cassation", "ca": "Cour d'appel"}


def _tete(d: dict) -> str:
    jur = d.get("jurisdiction")
    champs = (_JURIDICTIONS.get(jur, jur), d.get("chamber"), d.get("formation"), d.get("location"),
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
