"""Tableaux de suivi d'un entraînement de A0 (`runs/<date>-a0/metrics.jsonl`) :
avancement et prévision, nuits, perte par tranche de pas et par source, points de contrôle.
Écrit `tableau.md` dans le dossier de l'entraînement et l'affiche.

`python -m ccm.train.tableau [nom]` (nom : a0 par défaut)."""

import json
import sys
from pathlib import Path

SOURCES = ["synthetique", "hotpot", "fquad_piaf", "droit", "finqa", "squad"]


def _table(entetes: list[str], lignes: list[list]) -> list[str]:
    out = ["| " + " | ".join(entetes) + " |", "|" + " --- |" * len(entetes)]
    return out + ["| " + " | ".join(str(x) for x in ligne) + " |" for ligne in lignes]


def _f(x, n=3):
    return "–" if x is None else f"{x:.{n}f}"


def tableau(run: Path, total: int, par_nuit: int) -> str:
    lignes = [json.loads(x) for x in (run / "metrics.jsonl").read_text("utf-8").splitlines()]
    pas = [r for r in lignes if r["etape"] == "pas"]
    out = [f"# Entraînement {run.name}", ""]

    # Nuits : une reprise ouvre une séance, l'arrêt (ou la dernière ligne) la ferme.
    seances, cur = [], None
    for r in lignes:
        if r["etape"] == "reprise":
            cur = {"reprise": r, "pas": [], "arret": None}
            seances.append(cur)
        elif cur is not None and r["etape"] == "pas":
            cur["pas"].append(r)
        elif cur is not None and r["etape"] == "arret":
            cur["arret"] = r
    rangs = []
    for s in seances:
        ps, a, rp = s["pas"], s["arret"], s["reprise"]
        if not ps:
            continue
        sec = ps[-1]["secondes"] - ps[0]["secondes"] or 1
        n = len(ps)
        debut = sum(p["perte"] for p in ps[:100]) / min(100, n)
        fin = sum(p["perte"] for p in ps[-100:]) / min(100, n)
        arret = ("fin d'époque" if a["fin_epoque"] else "heure") if a else "en cours ou panne"
        rangs.append([rp["nuit"], rp.get("heure", "–"), a["heure"] if a else "–",
                      f"{ps[0]['pas']}–{ps[-1]['pas']}", n, f"{16 * n / sec:.2f}",
                      f"{sum(p['jetons'] for p in ps) / sec:.0f}", f"{debut:.3f} → {fin:.3f}",
                      rp["pas_sautes"], arret])  # fmt: skip
    out += ["## Nuits", ""]
    out += _table(["nuit", "début", "fin", "pas", "nb pas", "contextes/s", "jetons/s",
                   "perte (100 premiers → derniers)", "pas sautés", "arrêt"], rangs)  # fmt: skip

    # Avancement.
    fait = pas[-1]["pas"] + 1 if pas else 0
    vitesse = None
    if rangs:
        ps = seances[-1]["pas"] or pas
        vitesse = len(ps) / max(1, ps[-1]["secondes"] - ps[0]["secondes"])
    sautes = sum(s["reprise"]["pas_sautes"] for s in seances)
    reste = total - fait
    out += ["", "## Avancement", ""]
    out += _table(["pas faits", "pas sautés", "total", "fait", "nuits faites", "nuits prévues",
                   "durée d'une époque à la vitesse actuelle"], [[
        fait, sautes, total, f"{100 * fait / total:.1f} %", len(rangs), total // par_nuit,
        f"{par_nuit / vitesse / 3600:.1f} h" if vitesse else "–"]])  # fmt: skip
    if vitesse:
        out += ["", f"Reste {reste} pas, soit {reste / vitesse / 3600:.1f} h à cette vitesse."]

    # Perte par tranche de 1 000 pas, et par source.
    tranches = {}
    for p in pas:
        t = tranches.setdefault(p["pas"] // 1000, {"tout": [], **{s: [] for s in SOURCES}})
        t["tout"].append(p["perte"])
        for s, x in p.get("sources", {}).items():
            t.setdefault(s, []).append(x)
    moy = lambda v: sum(v) / len(v) if v else None  # noqa: E731
    out += ["", "## Perte par tranche de 1 000 pas", ""]
    out += _table(["pas", "toutes", *SOURCES], [
        [f"{k * 1000}–{k * 1000 + 999}", _f(moy(t["tout"])), *(_f(moy(t[s])) for s in SOURCES)]
        for k, t in sorted(tranches.items())])  # fmt: skip

    pcs = [r for r in lignes if r["etape"] == "point_de_controle"]
    out += ["", "## Points de contrôle", ""]
    out += _table(["pas", "perte moyenne des 2 000 pas", "meilleur"],
                  [[r["pas"], _f(r["perte_fenetre"]), "oui" if r["meilleur"] else ""]
                   for r in pcs])  # fmt: skip
    return "\n".join(out) + "\n"


def main(nom: str = "a0") -> None:
    from ccm.config import load_config

    runs = sorted((Path(__file__).resolve().parents[2] / "runs").glob(f"*-{nom}"))
    if not runs:
        raise SystemExit(f"aucun entraînement *-{nom} dans runs/")
    par_nuit = load_config("finetune").chargeur.exemples_par_epoque // 16
    texte = tableau(runs[-1], 3 * par_nuit, par_nuit)
    (runs[-1] / "tableau.md").write_text(texte, encoding="utf-8")
    print(texte)


if __name__ == "__main__":
    main(*sys.argv[1:])
