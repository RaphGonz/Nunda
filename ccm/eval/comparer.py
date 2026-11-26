"""Comparaison de A0, A1 et B (phase 6, seuil : F1 de B ≥ 95 % de celui de A1 au niveau 0)
sur les mêmes exemples (corpus corrigé), et exemples de réponses citées, pour la page du
réglage fin de B (`ccm.train.courbe`).

`python -m ccm.eval.comparer` : écrit `comparaison.json` et `exemples.json` dans le dossier
du réglage fin de B. Les textes sont ceux que voient les modèles : noms en slots (⟨PER 0⟩),
nombres et dates en clair."""

import json
from pathlib import Path

from ccm.schema import _MARQUEUR

RUNS = Path(__file__).resolve().parents[2] / "runs"
EVALS = {
    "A0": RUNS / "2026-11-06-a0" / "eval-pas-018124-corrige",
    "A1": RUNS / "2026-11-08-a1" / "eval-pas-008378-corrige",
    "B": RUNS / "2026-11-25-b-fin" / "eval-pas-020625-corrige",
}
SEUIL_B = 0.95  # part du F1 de A1 (niveau 0)


def comparaison() -> dict:
    out = {}
    for nom, d in EVALS.items():
        r = json.loads((d / "resultats.json").read_text("utf-8"))
        out[nom] = {"pas": r["pas"], "hors_limite": r["hors_limite"],
                    "sources": {s: g["total"] for s, g in r["sources"].items()}}  # fmt: skip
    a1 = out["A1"]["sources"]["synthetique"]["f1"]
    b = out["B"]["sources"]["synthetique"]["f1"]
    out["seuil"] = {
        "part": SEUIL_B,
        "a1": a1,
        "b": b,
        "rapport": b / a1,
        "passe": b >= SEUIL_B * a1,
    }
    return out


def suites() -> dict[str, dict[str, dict]]:
    return {nom: {json.loads(x)["id"]: json.loads(x)
                  for x in (d / "suites.jsonl").read_text("utf-8").splitlines()}
            for nom, d in EVALS.items()}  # fmt: skip


def texte(tm, valeurs: dict[int, str]) -> str:
    def un(m):
        k = tm.marques[int(m.group(1))]
        if k.genre == "NOM":
            return f"⟨{k.type} {k.nom}⟩"
        v = valeurs.get(k.valeur_id, f"⟨{k.genre}⟩")
        if k.unite == "heure du jour" and v.isdigit():  # minutes depuis minuit
            return f"{int(v) // 60} h {int(v) % 60:02d}"
        return f"{v} [{k.unite}]" if k.genre == "NUM" and k.unite else v

    return _MARQUEUR.sub(un, tm.texte)


def choisir(ss: dict, source: str) -> list[str]:
    """Exemples « normaux » de `source` où B a la bonne suite et A0 ou A1 non, sinon ceux
    où B a la bonne suite."""
    b = ss["B"]
    ids = [i for i, r in b.items() if r["source"] == source and r["genre"] == "normal"
           and i in ss["A0"] and i in ss["A1"] and r["exacte"]]  # fmt: skip
    differe = [i for i in ids if not (ss["A0"][i]["exacte"] and ss["A1"][i]["exacte"])]
    return sorted(differe or ids)


def exemples(par_source: int = 1) -> list[dict]:
    from ccm.eval.a0 import chargeurs
    from ccm.train.a0 import _tokenizer

    ss = suites()
    voc, decouper = _tokenizer()
    out = []
    for src, ch in chargeurs(voc, decouper).items():
        voulus = choisir(ss, src)
        if not voulus:
            continue
        tirages = {t.exemple.id: t for t in ch().epoque(0, 1000)}
        pris = 0
        for i in voulus:
            t = tirages.get(i)
            if t is None:
                continue
            cites = set()
            for nom in EVALS:
                cites |= {int(p[2:]) for p in ss[nom][i]["suite"] if p.startswith("P:")}
            justes = set(t.exemple.justificatives)
            montrer = sorted(cites | justes)
            if len(montrer) > 12:
                continue
            props = {p.local: p for p in t.exemple.propositions}
            out.append({
                "source": src, "id": i,
                "question": texte(t.exemple.question, t.valeurs),
                "n_propositions": len(props),
                "propositions": [{"p": k, "texte": texte(props[k], t.valeurs),
                                  "justificative": k in justes} for k in montrer],
                "ref": ss["B"][i]["ref"],
                "suites": {nom: ss[nom][i]["suite"] for nom in EVALS},
                "f1": {nom: ss[nom][i].get("f1") for nom in EVALS},
            })  # fmt: skip
            pris += 1
            if pris == par_source:
                break
    return out


if __name__ == "__main__":
    dossier = EVALS["B"].parent
    (dossier / "comparaison.json").write_text(json.dumps(comparaison(), indent=1), "utf-8")
    ex = exemples()
    (dossier / "exemples.json").write_text(json.dumps(ex, indent=1, ensure_ascii=False), "utf-8")
    print(f"comparaison et {len(ex)} exemples : {dossier}")
