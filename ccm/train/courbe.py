"""Courbes de perte d'un affinage (A0, A1, B), sur tout l'entraînement (toutes les nuits) :
perte totale et perte par source, moyennes par tranche de 50 pas, début de chaque nuit
marqué. Écrit `perte.html` dans le dossier de l'entraînement (page autonome ; Chart.js
chargé depuis cdnjs).

`python -m ccm.train.courbe [nom]` (nom : a0 par défaut)."""

import json
import sys
from pathlib import Path

from ccm.train.tableau import SOURCES

TRANCHE = 50
MODELE = Path(__file__).with_name("courbe.html")
# Nom du modèle et description, par nom d'entraînement.
META = {
    "a0": (
        "A0",
        "SmolLM2-360M avec LoRA, réglé sur la tâche de citation. 3 époques de 9 062 pas"
        " de 16 contextes, une par nuit.",
    ),
    "a1": ("A1", "SmolLM2-360M avec LoRA, réglé sur la tâche de citation (A1)."),
    "b-fin": (
        "B",
        "B-S (110 M paramètres, pré-entraîné de zéro sur le corpus anonymisé), réglé sur la"
        " tâche de citation. 5 époques de 4 125 pas, en tranches de 2 h.",
    ),
}


def donnees(lignes: list[dict], total: int, sessions: list[int] | None = None) -> dict:
    pas = [r for r in lignes if r["etape"] == "pas"]
    out: dict = {"pas": [], "total": [], **{s: [] for s in SOURCES}}
    for i in range(0, len(pas), TRANCHE):
        c = pas[i : i + TRANCHE]
        out["pas"].append(c[-1]["pas"] + 1)
        out["total"].append(round(sum(x["perte"] for x in c) / len(c), 4))
        for s in SOURCES:
            v = [x["sources"][s] for x in c if s in x.get("sources", {})]
            out[s].append(round(sum(v) / len(v), 4) if v else None)
    # Début de chaque session : `sessions.json` s'il existe (une session faite de
    # plusieurs tranches), sinon chaque reprise à un pas nouveau.
    out["nuits"] = sessions or sorted({r["pas"] for r in lignes if r["etape"] == "reprise"})
    out["total_pas"] = total
    return out


def page(lignes: list[dict], total: int, nom: str = "a0", sessions: list[int] | None = None) -> str:
    d = donnees(lignes, total, sessions)
    modele, desc = META.get(nom, (nom.upper(), ""))
    fr = lambda x: f"{x:.2f}".replace(".", ",")  # noqa: E731
    n = lambda x: f"{x:,}".replace(",", " ")  # noqa: E731
    remplace = {
        "__DATA__": json.dumps(d),
        "__DEBUT__": fr(d["total"][0]) if d["total"] else "–",
        "__FIN__": fr(d["total"][-1]) if d["total"] else "–",
        "__PAS__": n(d["pas"][-1] if d["pas"] else 0),
        "__TOTAL__": n(total),
        "__NUITS__": str(len(d["nuits"])),
        "__MODELE__": modele,
        "__DESC__": desc,
    }
    texte = MODELE.read_text(encoding="utf-8")
    for k, v in remplace.items():
        texte = texte.replace(k, v)
    return texte


def main(nom: str = "a0") -> Path:
    from ccm.train.tableau import plan

    run = sorted((Path(__file__).resolve().parents[2] / "runs").glob(f"*-{nom}"))[-1]
    lignes = [json.loads(x) for x in (run / "metrics.jsonl").read_text("utf-8").splitlines()]
    total = plan(run)[0]
    sortie = run / "perte.html"
    s = run / "sessions.json"
    sessions = json.loads(s.read_text("utf-8")) if s.exists() else None
    sortie.write_text(page(lignes, total, nom, sessions), encoding="utf-8")
    print(f"courbes : {sortie}")
    return sortie


if __name__ == "__main__":
    main(*sys.argv[1:2])
