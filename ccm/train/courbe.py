"""Courbes de perte d'un affinage (A0, A1, B), sur tout l'entraînement (toutes les nuits) :
perte totale et perte par source, moyennes par tranche de 50 pas, début de chaque nuit
marqué. Écrit `perte.html` dans le dossier de l'entraînement (page autonome ; Chart.js
chargé depuis cdnjs).

`python -m ccm.train.courbe [nom]` (nom : a0 par défaut)."""

import json
import sys
from html import escape
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


def comparaison_html(c: dict | None) -> str:
    """Tableau A0 / A1 / B (`comparaison.json`, `ccm.eval.comparer`)."""
    if not c:
        return ""
    f = lambda x: "–" if x is None else f"{x:.3f}".replace(".", ",")  # noqa: E731
    lignes = []
    for nom in ("A0", "A1", "B"):
        sy, hp = c[nom]["sources"]["synthetique"], c[nom]["sources"]["hotpot"]
        cases = [sy["f1"], sy["exactes"], sy["abstention"], hp["f1"], hp["exactes"],
                 hp["abstention_a_tort"]]  # fmt: skip
        tds = "".join(f"<td>{f(x)}</td>" for x in cases)
        lignes.append(f"<tr><td>{nom}</td>{tds}<td>{c[nom]['hors_limite']}</td></tr>")
    s = c["seuil"]
    classe, verdict = ("ok", "atteint") if s["passe"] else ("non", "non atteint")
    pc = f"{100 * s['rapport']:.1f}".replace(".", ",")
    return (
        "<section><h2>B contre A0 et A1</h2><p>Mêmes exemples de validation pour les trois"
        " modèles (corpus corrigé : synthétique de niveau 0 et HotpotQA), décodage glouton"
        " sous le masque. Un exemple trop long pour le modèle compte faux (« hors limite »)."
        "</p><p>Seuil de la phase 6 : F1 de B au niveau 0 ≥ 95 % de celui de A1. B fait"
        f' <b class="{classe}">{pc} %</b> de A1 : {verdict}.</p>'
        '<div class="tab"><table><thead><tr><th>Modèle</th><th>F1 niveau 0</th>'
        "<th>Exactes</th><th>Abstention</th><th>F1 HotpotQA</th><th>Exactes</th>"
        "<th>Abst. à tort</th><th>Hors limite</th></tr></thead><tbody>"
        + "".join(lignes)
        + "</tbody></table></div></section>"
    )


def exemples_html(ex: list[dict] | None) -> str:
    """Réponses citées de A0, A1 et B sur un même exemple (`exemples.json`)."""
    if not ex:
        return ""
    blocs = []
    for x in ex:
        props = "".join(
            f'<li class="{"j" if p["justificative"] else ""}"><span>P:{p["p"]}</span>'
            f"{escape(p['texte'])}</li>"
            for p in x["propositions"]
        )
        rep = "".join(
            f"<tr><td>{n}</td><td><code>{escape(' '.join(s))}</code></td></tr>"
            for n, s in [("Attendu", x["ref"]), *x["suites"].items()]
        )
        blocs.append(
            f'<div class="ex"><p class="q">{escape(x["question"])}</p>'
            f"<p>{x['source']} · {x['n_propositions']} propositions dans le contexte ;"
            " ci-dessous les justificatives (en clair) et les autres citées par un modèle"
            f" (en gris).</p><ol>{props}</ol>"
            f'<div class="tab"><table><tbody>{rep}</tbody></table></div></div>'
        )
    return (
        "<section><h2>Exemples de réponses</h2><p>Ce que voient les modèles : noms remplacés"
        " par des slots, nombres et dates en clair. Une réponse est une suite d'actions"
        " (citer P:n, ET, FIN…), jamais du texte libre.</p>" + "".join(blocs) + "</section>"
    )


def page(lignes: list[dict], total: int, nom: str = "a0", sessions: list[int] | None = None,
         extra: str = "") -> str:  # fmt: skip
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
        "__EXTRA__": extra,
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
    lus = [json.loads((run / f).read_text("utf-8")) if (run / f).exists() else None
           for f in ("comparaison.json", "exemples.json")]  # fmt: skip
    extra = comparaison_html(lus[0]) + exemples_html(lus[1])
    sortie.write_text(page(lignes, total, nom, sessions, extra), encoding="utf-8")
    print(f"courbes : {sortie}")
    return sortie


if __name__ == "__main__":
    main(*sys.argv[1:2])
