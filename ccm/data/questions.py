"""Questions de l'enseignant sur Légifrance et Judilibre (SPEC.md §12, « Modèle enseignant »).

Un passage par article ou par décision ; les deux sources alternent. Chaque passage fait trois
appels : la question, puis le second passage avec les justificatives seules, puis sans elles.
Une ligne JSON par passage dans `questions.jsonl` ; une relance reprend après la dernière ligne.

    uv run ccm questions
"""

import json
import random
import re
import sqlite3
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ccm.data.enseignant import (
    _SCHEMA,
    _SCHEMA_OUI_NON,
    MODELES,
    PORT,
    SERVEUR,
    _appel,
    _attendre_serveur,
    numeros_valides,
    prompt_confirmation,
    prompt_question,
)

MODELE = "qwen3.5-27b"
GRAINE = 20261103
NATURE = {"legi": "d'un texte de loi français", "jud": "d'une décision de justice française"}
# Passages de décision écartés : ils citent souvent une personne (avocat, magistrat, greffier).
_PERSONNE = re.compile(
    r"\b(ma[iî]tre|me |avocat|greffi|pr[ée]siden|conseill|magistrat|rapporteur|procureur)",
    re.IGNORECASE,
)


def _bon_passage(textes: list[str]) -> bool:
    return 3 <= len(textes) <= 8 and 400 <= sum(map(len, textes)) <= 1800


def fenetre_decision(props: list[tuple[int, str, str]], rng: random.Random) -> list[int]:
    """Indices d'une suite de 3 à 8 PHRASE consécutives, 400 à 1 800 caractères, sans personne.

    `props` : (prop_id, genre, texte) dans l'ordre de la décision. Liste vide si aucune.
    """
    candidates = []
    for debut in range(len(props)):
        for fin in range(debut + 3, min(debut + 8, len(props)) + 1):
            bloc = props[debut:fin]
            textes = [t for _, g, t in bloc]
            if any(g != "PHRASE" or _PERSONNE.search(t) for _, g, t in bloc):
                break
            if _bon_passage(textes):
                candidates.append(list(range(debut, fin)))
    return rng.choice(candidates) if candidates else []


def passages(base: Path, graine: int = GRAINE, sauter: frozenset[str] = frozenset()):
    """Un générateur de passages (source, piece, [prop_id], [texte]) par source.

    Les pièces de `sauter` sont omises sans être lues : la reprise reste rapide.
    """
    c = sqlite3.connect(f"file:{base.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    legi = sorted(
        r[0]
        for r in c.execute(
            "SELECT piece_id FROM proposition WHERE piece_id LIKE 'LEGIARTI%' GROUP BY piece_id "
            "HAVING SUM(genre = 'PHRASE') BETWEEN 3 AND 8 "
            "AND SUM(LENGTH(texte)) BETWEEN 400 AND 1800"
        )
    )
    jud = sorted(
        r[0] for r in c.execute("SELECT piece_id FROM piece WHERE piece_id LIKE 'judilibre-%'")
    )
    rng = random.Random(graine)
    rng.shuffle(legi)
    rng.shuffle(jud)

    def lire(piece: str) -> list[tuple[int, str, str]]:
        return c.execute(
            "SELECT prop_id, genre, texte FROM proposition WHERE piece_id = ? ORDER BY page, ordre",
            (piece,),
        ).fetchall()

    def de_legi():
        for piece in legi:
            if piece in sauter:
                continue
            p = lire(piece)
            yield "legi", piece, [x[0] for x in p], [x[2] for x in p]

    def de_jud():
        for piece in jud:
            if piece in sauter:
                continue
            p = lire(piece)
            idx = fenetre_decision(p, random.Random(f"{graine}-{piece}"))
            if idx:
                yield "jud", piece, [p[i][0] for i in idx], [p[i][2] for i in idx]

    return {"legi": de_legi(), "jud": de_jud()}


def traiter(source: str, piece: str, ids: list[int], textes: list[str]) -> dict:
    """Question, puis second passage du §12 ; `gardee` dit si l'exemple passe."""
    sortie, _, _ = _appel(prompt_question(textes, NATURE[source]), _SCHEMA)
    ligne = {"source": source, "piece": piece, "prop_ids": ids, "sortie": sortie}
    just = sortie["justificatives"] if sortie else []
    if not sortie:
        ligne["rejet"] = "json"
    elif not numeros_valides(just, len(textes)):
        ligne["rejet"] = "numeros"
    else:
        avec = [(i, textes[i - 1]) for i in just]
        sans = [(i, t) for i, t in enumerate(textes, 1) if i not in just]
        a, _, _ = _appel(prompt_confirmation(sortie["question"], avec), _SCHEMA_OUI_NON)
        b, _, _ = _appel(prompt_confirmation(sortie["question"], sans), _SCHEMA_OUI_NON)
        ligne["avec"], ligne["sans"] = a, b
        if not (a and a["reponse_possible"]):
            ligne["rejet"] = "pas_de_reponse_avec"
        elif not b or b["reponse_possible"]:
            ligne["rejet"] = "reponse_sans"
    ligne["gardee"] = "rejet" not in ligne
    return ligne


def generer(racine: Path, cible: int = 20_000, paralleles: int = 4, nom: str = "questions") -> Path:
    """Écrit `racine/enseignant/<nom>.jsonl` jusqu'à `cible` exemples gardés, moitié par source."""
    sortie = racine / "enseignant" / f"{nom}.jsonl"
    faits, gardes = set(), {"legi": 0, "jud": 0}
    if sortie.exists():
        for ligne in sortie.read_text(encoding="utf-8").splitlines():
            d = json.loads(ligne)
            faits.add(d["piece"])
            gardes[d["source"]] += d["gardee"]
    quota = {"legi": cible // 2, "jud": cible - cible // 2}
    verrou = threading.Lock()
    journal = (racine / "enseignant" / f"{MODELE}-serveur.log").open("a", encoding="utf-8")
    serveur = subprocess.Popen(
        [racine / SERVEUR, "-m", racine / MODELES[MODELE], "--port", str(PORT), "-ngl", "99"]
        + ["-c", str(4096 * paralleles), "--parallel", str(paralleles), "--reasoning", "off"],
        stdout=journal,
        stderr=subprocess.STDOUT,
    )
    try:
        _attendre_serveur(serveur)
        with sortie.open("a", encoding="utf-8") as f, ThreadPoolExecutor(paralleles) as pool:

            def tache(p):
                if gardes[p[0]] >= quota[p[0]]:
                    return
                d = traiter(*p)
                with verrou:
                    gardes[d["source"]] += d["gardee"]
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
                    f.flush()

            en_cours = []
            sources = passages(racine / "droit.sqlite", sauter=frozenset(faits))
            while sources:
                for nom_source, gen in list(sources.items()):
                    p = next(gen, None)
                    if p is None or gardes[nom_source] >= quota[nom_source]:
                        del sources[nom_source]
                        continue
                    if p[1] in faits:
                        continue
                    en_cours.append(pool.submit(tache, p))
                    if len(en_cours) >= 4 * paralleles:
                        en_cours.pop(0).result()
            for t in en_cours:
                t.result()
    finally:
        serveur.terminate()
        serveur.wait(timeout=60)
        journal.close()
    return sortie
