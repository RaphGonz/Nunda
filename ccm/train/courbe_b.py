"""Page de suivi du pré-entraînement de B (§13) : L_pré et ses trois termes, moyennes par
tranche de 50 pas, validation tous les 1 000 pas, début de chaque session marqué
(`sessions.json`), pas refaits après une reprise comptés une fois, avancement.
Écrit `perte.html` dans le dossier de l'entraînement (page autonome ; Chart.js chargé depuis
cdnjs).

`python -m ccm.train.courbe_b [dossier]` (dossier : le dernier `runs/*-b`)."""

import json
import sys
from pathlib import Path

TRANCHE = 50
MODELE = Path(__file__).with_name("courbe_b.html")
TERMES = ("mots", "pointeur", "attributs")
POIDS = {"mots": 1.0, "pointeur": 1.0, "attributs": 0.5}  # §13


def _pre(x: dict, pre: str = "") -> float:
    return sum(w * x[pre + k] for k, w in POIDS.items())


def garder(lignes: list[dict]) -> list[dict]:
    """Une ligne par pas : une reprise depuis un point plus ancien remplace les pas refaits.
    Chaque ligne reçoit `dt`, ses secondes de calcul (écart du chronomètre `s`, qui repart de
    zéro à chaque lancement)."""
    out: list[dict] = []
    prec = None
    for x in lignes:
        dt = x["s"] - prec["s"] if prec and x["s"] >= prec["s"] else x["s"]
        prec = x
        while out and out[-1]["pas"] >= x["pas"]:
            out.pop()
        out.append(x | {"dt": dt})
    return out


def donnees(lignes: list[dict], total: int, sessions: list[int] | None = None) -> dict:
    """`sessions` : premier pas de chaque session (une session peut compter plusieurs
    lancements, ex. tranches de 2 h) ; à défaut, chaque lancement en ouvre une."""
    lignes = garder(lignes)
    out: dict = {"pas": [], "pre": [], **{k: [] for k in TERMES}, "total_pas": total}
    for i in range(0, len(lignes), TRANCHE):
        c = lignes[i : i + TRANCHE]
        out["pas"].append(c[-1]["pas"])
        out["pre"].append(round(sum(_pre(x) for x in c) / len(c), 4))
        for k in TERMES:
            out[k].append(round(sum(x[k] for x in c) / len(c), 4))
    v = [x for x in lignes if "val_mots" in x]
    out["val"] = {"pas": [x["pas"] for x in v], "pre": [round(_pre(x, "val_"), 4) for x in v],
                  **{k: [round(x["val_" + k], 4) for x in v] for k in TERMES}}  # fmt: skip
    if sessions is None:
        sessions = [b["pas"] for a, b in zip([None, *lignes], lignes, strict=False)
                    if a is None or b["dt"] == b["s"]]  # fmt: skip
    out["nuits"] = [p - 1 for p in sessions]
    out["heures"] = sum(x["dt"] for x in lignes) / 3600
    return out


def page(lignes: list[dict], total: int, sessions: list[int] | None = None) -> str:
    d = donnees(lignes, total, sessions)
    fr = lambda x, n=2: f"{x:.{n}f}".replace(".", ",")  # noqa: E731
    nb = lambda x: f"{x:,}".replace(",", " ")  # noqa: E731
    pas = d["pas"][-1] if d["pas"] else 0
    reste = d["heures"] / pas * (total - pas) if pas else 0.0
    remplace = {
        "__DATA__": json.dumps(d),
        "__DEBUT__": fr(d["pre"][0]) if d["pre"] else "–",
        "__FIN__": fr(d["pre"][-1]) if d["pre"] else "–",
        "__VAL__": fr(d["val"]["pre"][-1]) if d["val"]["pre"] else "–",
        "__PAS__": nb(pas),
        "__TOTAL__": nb(total),
        "__PCT__": fr(100 * pas / total, 1),
        "__HEURES__": fr(d["heures"], 1),
        "__RESTE__": fr(reste, 1),
        "__NUITS__": str(len(d["nuits"])),
    }
    texte = MODELE.read_text(encoding="utf-8")
    for k, v in remplace.items():
        texte = texte.replace(k, v)
    return texte


def main(dossier: str | None = None) -> Path:
    runs = Path(__file__).resolve().parents[2] / "runs"
    run = Path(dossier) if dossier else sorted(runs.glob("*-b"))[-1]
    lignes = [json.loads(x) for x in (run / "metrics.jsonl").read_text("utf-8").splitlines()]
    total = json.loads((run / "plan.json").read_text())["pas_total"]
    s = run / "sessions.json"  # facultatif : premier pas de chaque session
    sessions = json.loads(s.read_text()) if s.exists() else None
    sortie = run / "perte.html"
    sortie.write_text(page(lignes, total, sessions), encoding="utf-8")
    print(f"courbes : {sortie}")
    return sortie


if __name__ == "__main__":
    main(*sys.argv[1:2])
