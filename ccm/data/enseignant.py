"""Comparaison des modèles enseignants (SPEC.md §12, §16) sur des articles de Légifrance.

llama.cpp sert chaque modèle en 4 bits (Q4_K_M), en local. Le prompt et les contrôles suivent
le §12 : JSON (question, justificatives, connecteurs), au plus 4 justificatives, puis un second
passage : réponse possible avec les justificatives seules, impossible sans elles.

    uv run ccm enseignant
"""

import json
import random
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path

PORT = 8091
SERVEUR = "llama.cpp/b12048/llama-server.exe"
MODELES = {
    "qwen2.5-7b": "modeles/enseignant/qwen2.5-7b/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
    "mistral-7b-v0.3": "modeles/enseignant/mistral-7b-v0.3/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
    "qwen2.5-14b": "modeles/enseignant/qwen2.5-14b/qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf",
    "qwen2.5-32b": "modeles/enseignant/qwen2.5-32b/qwen2.5-32b-instruct-q4_k_m-00001-of-00005.gguf",
    "qwen3-32b": "modeles/enseignant/qwen3-32b/Qwen3-32B-Q4_K_M.gguf",
    "qwen3.5-27b": "modeles/enseignant/qwen3.5-27b/Qwen_Qwen3.5-27B-Q4_K_M.gguf",
    "qwen3.5-35b-a3b": "modeles/enseignant/qwen3.5-35b-a3b/Qwen_Qwen3.5-35B-A3B-Q4_K_M.gguf",
}
CONNECTEURS = ["ET", "MAIS", "EN_REVANCHE", "PAR_AILLEURS"]
_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "justificatives": {"type": "array", "items": {"type": "integer"}},
        "connecteurs": {"type": "array", "items": {"enum": CONNECTEURS}},
    },
    "required": ["question", "justificatives", "connecteurs"],
}
_SCHEMA_OUI_NON = {
    "type": "object",
    "properties": {"reponse_possible": {"type": "boolean"}},
    "required": ["reponse_possible"],
}


def extraits(base: Path, n: int = 10, graine: int = 20261102) -> list[dict]:
    """Tire `n` articles de 3 à 8 phrases et de 400 à 1 800 caractères, sans regarder le texte."""
    c = sqlite3.connect(f"file:{base.as_posix()}?mode=ro", uri=True)
    ids = sorted(
        r[0]
        for r in c.execute(
            "SELECT piece_id FROM proposition WHERE piece_id LIKE 'LEGIARTI%' GROUP BY piece_id "
            "HAVING SUM(genre = 'PHRASE') BETWEEN 3 AND 8 "
            "AND SUM(LENGTH(texte)) BETWEEN 400 AND 1800"
        )
    )
    rendu = []
    for piece in random.Random(graine).sample(ids, n):
        lignes = c.execute(
            "SELECT texte FROM proposition WHERE piece_id = ? ORDER BY page, ordre", (piece,)
        )
        rendu.append({"piece": piece, "props": [r[0] for r in lignes]})
    c.close()
    return rendu


def _numerotees(props: list[tuple[int, str]]) -> str:
    return "\n".join(f"[{i}] {t}" for i, t in props)


def prompt_question(props: list[str], nature: str = "d'un texte de loi français") -> str:
    return (
        f"Voici les propositions numérotées {nature}.\n\n"
        f"{_numerotees(list(enumerate(props, 1)))}\n\n"
        "Écris en français une question précise dont la réponse se trouve dans ces propositions. "
        "Rends un JSON : `question` ; `justificatives`, les numéros des propositions nécessaires "
        "pour répondre (4 au plus) ; `connecteurs`, la liste des connecteurs entre ces "
        f"propositions, à choisir parmi {', '.join(CONNECTEURS)}."
    )


def prompt_confirmation(question: str, props: list[tuple[int, str]]) -> str:
    return (
        f"Propositions :\n{_numerotees(props) or '(aucune)'}\n\nQuestion : {question}\n\n"
        "En te fondant uniquement sur ces propositions, peut-on répondre à la question ? "
        "Rends un JSON avec le booléen `reponse_possible`."
    )


def numeros_valides(justificatives: list[int], nb_props: int) -> bool:
    """Règle du §12 : des numéros existants, distincts, de 1 à 4."""
    return (
        1 <= len(justificatives) <= 4
        and len(set(justificatives)) == len(justificatives)
        and all(1 <= j <= nb_props for j in justificatives)
    )


def _appel(contenu: str, schema: dict) -> tuple[dict | None, float, int]:
    corps = {
        "messages": [{"role": "user", "content": contenu}],
        "temperature": 0,
        "seed": 0,
        "max_tokens": 400,
        "response_format": {"type": "json_schema", "json_schema": {"schema": schema}},
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        json.dumps(corps).encode(),
        {"Content-Type": "application/json"},
    )
    debut = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    duree = time.perf_counter() - debut
    try:
        rendu = json.loads(d["choices"][0]["message"]["content"])
    except json.JSONDecodeError:
        rendu = None
    return rendu, duree, d["usage"]["completion_tokens"]


def _vram_mio() -> int:
    s = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(s.stdout.strip())


def _attendre_serveur(p: subprocess.Popen) -> None:
    for _ in range(300):
        if p.poll() is not None:
            raise RuntimeError(f"llama-server arrêté, code {p.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise TimeoutError("llama-server ne répond pas")


def evaluer(racine: Path, nom: str, textes: list[dict]) -> dict:
    """Lance un modèle sur tous les extraits ; le serveur s'arrête ensuite."""
    vram_avant = _vram_mio()
    pic = vram_avant
    with (racine / "enseignant" / f"{nom}.log").open("w", encoding="utf-8") as journal:
        p = subprocess.Popen(
            [racine / SERVEUR, "-m", racine / MODELES[nom], "--port", str(PORT), "-ngl", "99"]
            + ["-c", "8192", "--parallel", "1", "--reasoning", "off"],
            stdout=journal,
            stderr=subprocess.STDOUT,
        )
        try:
            _attendre_serveur(p)
            lignes = []
            secondes = jetons = 0.0
            for t in textes:
                props = t["props"]
                sortie, s, j = _appel(prompt_question(props), _SCHEMA)
                secondes, jetons = secondes + s, jetons + j
                ligne = {"piece": t["piece"], "sortie": sortie, "gardee": False}
                just = sortie["justificatives"] if sortie else []
                if sortie and numeros_valides(just, len(props)):
                    ligne["numeros_valides"] = True
                    avec = [(i, props[i - 1]) for i in just]
                    sans = [(i, x) for i, x in enumerate(props, 1) if i not in just]
                    a, s1, j1 = _appel(
                        prompt_confirmation(sortie["question"], avec), _SCHEMA_OUI_NON
                    )
                    b, s2, j2 = _appel(
                        prompt_confirmation(sortie["question"], sans), _SCHEMA_OUI_NON
                    )
                    secondes, jetons = secondes + s1 + s2, jetons + j1 + j2
                    ligne["avec"], ligne["sans"] = a, b
                    ligne["gardee"] = bool(
                        a and b and a["reponse_possible"] and not b["reponse_possible"]
                    )
                lignes.append(ligne)
                pic = max(pic, _vram_mio())
        finally:
            p.terminate()
            p.wait(timeout=30)
    return {
        "modele": nom,
        "vram_avant_mio": vram_avant,
        "vram_pic_mio": pic,
        "secondes": round(secondes, 1),
        "jetons": int(jetons),
        "jetons_par_seconde": round(jetons / secondes, 1),
        "gardees": sum(x["gardee"] for x in lignes),
        "lignes": lignes,
    }


def comparer(racine: Path, modeles: list[str], n: int = 10, nom: str = "comparaison") -> Path:
    """Écrit `racine/enseignant/<nom>.json`. Les `n` premiers extraits ne dépendent pas de `n`."""
    (racine / "enseignant").mkdir(exist_ok=True)
    textes = extraits(racine / "droit.sqlite", n)
    res = {"extraits": textes, "modeles": [evaluer(racine, m, textes) for m in modeles]}
    cible = racine / "enseignant" / f"{nom}.json"
    cible.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return cible
