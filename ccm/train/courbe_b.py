"""Page de suivi du pré-entraînement de B (§13) : L_pré et ses trois termes, moyennes par
tranche de 50 pas, validation tous les 1 000 pas, début de chaque nuit marqué, avancement.
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


def donnees(lignes: list[dict], total: int) -> dict:
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
    # Une nuit commence quand le chronomètre `s` (depuis le lancement) repart de zéro.
    nuits, secondes = [], 0.0
    for a, b in zip([None, *lignes], lignes, strict=False):
        if a is None or b["s"] < a["s"]:
            nuits.append(b["pas"] - 1)
            secondes += a["s"] if a else 0.0
    secondes += lignes[-1]["s"] if lignes else 0.0
    out["nuits"], out["heures"] = nuits, secondes / 3600
    return out


def page(lignes: list[dict], total: int) -> str:
    d = donnees(lignes, total)
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
    sortie = run / "perte.html"
    sortie.write_text(page(lignes, total), encoding="utf-8")
    print(f"courbes : {sortie}")
    return sortie


if __name__ == "__main__":
    main(*sys.argv[1:2])
