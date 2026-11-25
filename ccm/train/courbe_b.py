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


def canaris_html(res: dict | None) -> str:
    """Tableau des canaris (§14) : extraction avec le vrai nom, avec un nom témoin, et l'écart
    (fuite), par genre et fréquence."""
    if not res:
        return ""
    pc = lambda x: f"{100 * x:.1f}".replace(".", ",") + " %"  # noqa: E731
    rg = lambda x: f"{x:.0f}"  # noqa: E731
    g = res["par_groupe"]
    lignes = []
    for genre, nom in (("naturel", "Naturels"), ("force", "Forcés")):
        for f in (1, 10, 100):
            x = g.get(f"{genre}-{f}")
            if x and "extraction_temoin" in x:
                lignes.append(
                    f"<tr><td>{nom}</td><td>{f}</td><td>{pc(x['extraction'])}</td>"
                    f"<td>{pc(x['extraction_temoin'])}</td><td><b>{pc(x['extraction_nette'])}</b>"
                    f"</td><td>{rg(x['rang_moyen'])} / {rg(x['rang_moyen_temoin'])}</td></tr>"
                )
    if not lignes:
        return ""
    return (
        "<section><h2>Canaris</h2><p>De faux faits sur des personnes inventées, cachés dans le "
        "corpus (« Selon ses proches, X a pour mot fétiche sulfamide »). Après l'entraînement, "
        "on demande au modèle la fin de la phrase parmi 1 000 mots. <b>Naturels</b> : passés "
        "par l'anonymisation (ce qui fuit malgré elle). <b>Forcés</b> : nom laissé en clair (ce "
        "qui fuirait sans elle). Chaque phrase est aussi posée avec 5 noms <b>témoins</b> "
        "jamais vus : ce que la phrase seule donne. <b>Fuite</b> = extraction avec le vrai nom "
        "moins extraction avec un témoin ; c'est ce que les poids ont retenu du nom.</p>"
        "<table><thead><tr><th>Canaris</th><th>Répétitions</th><th>Vrai nom</th>"
        "<th>Témoin</th><th>Fuite</th><th>Rang moyen (vrai / témoin)</th></tr></thead><tbody>"
        + "".join(lignes)
        + "</tbody></table></section>"
    )


def generation_html(ex: list[dict] | None) -> str:
    """Exemples de génération libre : début donné (gras), suite produite par B."""
    if not ex:
        return ""
    from html import escape

    blocs = "".join(
        f"<blockquote><b>{escape(x['debut'])}</b>{escape(x['suite'])}</blockquote>" for x in ex
    )
    return (
        "<section><h2>Exemples de génération</h2><p>Suites libres produites par B au dernier "
        "point, sans retouche (température 0,8, top-p 0,9, graine fixe). Les ⟨PER⟩, ⟨LIEU⟩, "
        "⟨NUM⟩… sont les places des noms et des valeurs : B n'écrit jamais un nom lui-même, il "
        "le pointera plus tard dans les sources.</p>" + blocs + "</section>"
    )


def page(lignes: list[dict], total: int, sessions: list[int] | None = None,
         canaris: dict | None = None, generation: list[dict] | None = None) -> str:  # fmt: skip
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
        "__CANARIS__": canaris_html(canaris) + generation_html(generation),
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
    c = run / "canaris.json"  # facultatif : sortie de `ccm pretrain canaris-b`
    canaris = json.loads(c.read_text()) if c.exists() else None
    g = run / "generation.json"  # facultatif : sortie de `ccm pretrain generer-b`
    generation = json.loads(g.read_text("utf-8")) if g.exists() else None
    sortie = run / "perte.html"
    sortie.write_text(page(lignes, total, sessions, canaris, generation), encoding="utf-8")
    print(f"courbes : {sortie}")
    return sortie


if __name__ == "__main__":
    main(*sys.argv[1:2])
