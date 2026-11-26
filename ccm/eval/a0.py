"""Mesures de A0 et de A1 (SPEC.md §2, seuil de la phase 4 ; §14, « Citation », « Abstention ») sur
les parties de validation : corpus synthétique niveau 0 et HotpotQA (distracteurs).

Les exemples sont tirés par le chargeur de l'entraînement (mêmes parts d'abstention, de
conflit injecté et de contrefactuel), sur les parties de validation ; décodage glouton sous
le masque (`DecodeurA0`).

En A1 (`variante="a1"`), mêmes exemples, en-tête [REL] retiré. Le décodage d'un exemple
s'arrête si son entrée (contexte et suite déjà produite) dépasse 2 500 jetons : il compte
comme une réponse fausse (aucune citation, pas d'abstention) dans « total », et la ligne
« dans_limite » donne les mesures sans lui.

Corpus corrigé (`corrige=True`, décision de Raphael du 2026-11-11) : avant le décodage, on
retire les exemples écartés à l'entraînement de A1 (entrée sans [REL] > 2 500 jetons), pour
A0 comme pour A1 : les deux modèles sont mesurés sur les mêmes exemples. Sortie dans
`eval-<point>-corrige/`.

En B (`variante="b"`, phase 6) : B-S réglé (`ccm.train.b_fin`), BPE de B, limite de 2 048 jetons
(même règle « hors limite » qu'A1). Corpus corrigé : les mêmes exemples que A1 (identifiants
lus dans `EVAL_A1_CORRIGE`), le filtre de longueur de A1 dépendant du découpage de SmolLM2.

`python -m ccm.eval.a0 [point_de_controle] [n_synthetique] [n_hotpot] [a0|a1] [corrige]`
(par défaut : le dernier point de contrôle du dernier entraînement, 1 000 et 1 000) : écrit
`eval-<point>/resultats.json`, `suites.jsonl` et `rapport.md` à côté du point de contrôle,
puis affiche le rapport."""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import torch

from ccm.grammar.automaton import Contexte
from ccm.train.chargeur import Tirage

VAL_SYNTH = Path("runs/corpus/niveau0-val/validation")
SEUILS = {"synthetique": {"f1": 0.90, "abstention": 0.85}, "hotpot": {"f1": 0.75}}
ABST = ("abstention", "abstention_contexte")
EVAL_A1_CORRIGE = Path("runs/2026-11-08-a1/eval-pas-008378-corrige/suites.jsonl")


def chargeurs(voc, decouper) -> dict:
    """Un chargeur par source de validation (seule source, poids 1)."""
    from ccm.config import load_config
    from ccm.data import hotpot
    from ccm.train.chargeur import Chargeur, SourcePublique, SourceSynthetique, ZonesCache

    icfg, dcfg = load_config("ingest"), load_config("donnees")
    cfg = load_config("finetune").chargeur
    brut = dcfg.racine / "brut"
    sources = {
        "synthetique": lambda: SourceSynthetique.depuis_corpus(VAL_SYNTH, icfg),
        "hotpot": lambda: SourcePublique(list(hotpot.lire(brut / "hotpot", "validation")),
                                         ZonesCache(dcfg.racine / "cache-zones-en.sqlite"), icfg),
    }  # fmt: skip
    out = {}
    for nom, src in sources.items():
        c = cfg.model_copy(update={"poids": {nom: 1.0}})
        out[nom] = lambda nom=nom, src=src, c=c: Chargeur(
            {nom: src()}, c, icfg, load_config("search"), load_config("grammar"), voc, decouper
        )
    return out


def citees(suite: list[str]) -> set[int]:
    return {int(p[2:]) for p in suite if p.startswith("P:")}


def mesure(t: Tirage, suite: list[str]) -> dict:
    ref = list(t.exemple.cible)
    r = {"source": t.source, "genre": t.genre, "id": t.exemple.id, "suite": suite, "ref": ref,
         "exacte": suite == ref, "abst_ref": ref[0] == "ABSTENTION",
         "abst": suite[0] == "ABSTENTION"}  # fmt: skip
    if not r["abst_ref"]:
        c, j = citees(suite), set(t.exemple.justificatives)
        p = len(c & j) / len(c) if c else 0.0
        rr = len(c & j) / len(j) if j else 0.0
        r |= {"p": p, "r": rr, "f1": 2 * p * rr / (p + rr) if p + rr else 0.0}
    return r


def bilan(rs: list[dict]) -> dict:
    rep = [r for r in rs if not r["abst_ref"]]
    sans = [r for r in rs if r["abst_ref"]]
    moy = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    return {
        "n": len(rs), "avec_reponse": len(rep), "sans_reponse": len(sans),
        "p": moy([r["p"] for r in rep]), "r": moy([r["r"] for r in rep]),
        "f1": moy([r["f1"] for r in rep]),
        "exactes": moy([r["exacte"] for r in rs]),
        "abstention": moy([r["abst"] for r in sans]),
        "abstention_a_tort": moy([r["abst"] for r in rep]),
    }  # fmt: skip


def rapport(nom: str, res: dict, variante: str = "a0") -> str:
    f = lambda x: "–" if x is None else f"{x:.3f}"  # noqa: E731
    titre = f"# Mesures de {variante.upper()} : {nom}"
    if res.get("corrige"):
        titre += " — corpus corrigé (exemples de A1 > 2 500 jetons SmolLM2 retirés)"
    out = [titre, "", "## Seuils de la phase 4 (validation)", "",
           "| Source | Mesure | Seuil | Mesure | Passe |", "|" + " --- |" * 5]  # fmt: skip
    for src, seuils in SEUILS.items():
        for k, s in seuils.items():
            x = res["sources"].get(src, {}).get("total", {}).get(k)
            out.append(f"| {src} | {k} | {s:.2f} | {f(x)} | {'oui' if x and x >= s else 'non'} |")
    out += ["", "## Par source et par genre", "",
            "| Source | Genre | n | P | R | F1 | exactes | abstention | abst. à tort |",
            "|" + " --- |" * 9]  # fmt: skip
    for src, gs in res["sources"].items():
        for g, b in gs.items():
            out.append(
                f"| {src} | {g} | {b['n']} | {f(b['p'])} | {f(b['r'])} | {f(b['f1'])} | "
                f"{f(b['exactes'])} | {f(b['abstention'])} | {f(b['abstention_a_tort'])} |"
            )
    out += ["", f"Décodage : {res['secondes']:.0f} s pour {res['n']} exemples."]
    if res.get("hors_limite"):
        out.append(
            f"Hors limite (arrêtés à {2048 if variante == 'b' else 2500} jetons, faux dans"
            f" « total ») : {res['hors_limite']}."
        )
    return "\n".join(out) + "\n"


def evaluer(chemin: Path, n_synth: int = 1000, n_hotpot: int = 1000, variante: str = "a0",
            corrige: bool = False) -> dict:  # fmt: skip
    from ccm.config import load_config
    from ccm.model.a0 import charger_smollm
    from ccm.model.a1 import T_MAX, charger_smollm_a1, sans_rel
    from ccm.model.decodeur import DecodeurA0
    from ccm.train.a0 import SMOLLM, _tokenizer, recharger

    neg = load_config("ingest").conflits.negation
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    gcfg = load_config("grammar")
    a1, b = variante == "a1", variante == "b"
    garder = None
    if b:
        from ccm.train import b_fin

        voc, decouper, tok = b_fin.jetons_b()
        modele = b_fin.charger_modele(voc, tok, None, dev)
        pas = recharger(chemin, modele)
        dec = DecodeurA0(modele, voc, decouper, gcfg, b_fin.JETONS_LOT, None, b_fin.T_MAX)
        if corrige:
            lignes = EVAL_A1_CORRIGE.read_text("utf-8").splitlines()
            garder = {json.loads(x)["id"] for x in lignes}
    else:
        voc, decouper = _tokenizer()
        modele = (charger_smollm_a1 if a1 else charger_smollm)(voc, SMOLLM).to(dev)
        pas = recharger(chemin, modele)
        if a1:
            dec = DecodeurA0(modele, voc, decouper, gcfg, 4000, lambda e: sans_rel(e, voc), T_MAX)
        else:
            dec = DecodeurA0(modele, voc, decouper, gcfg)

    sortie = chemin.parent / f"eval-{chemin.stem}{'-corrige' if corrige else ''}"
    sortie.mkdir(exist_ok=True)
    rs, t0 = [], time.time()
    with (sortie / "suites.jsonl").open("w", encoding="utf-8") as fs:
        for src, ch in chargeurs(voc, decouper).items():
            n = {"synthetique": n_synth, "hotpot": n_hotpot}[src]
            tirages = list(ch().epoque(0, n))
            if garder is not None:
                tirages = [t for t in tirages if t.exemple.id in garder]
            elif corrige:
                tirages = [t for t in tirages
                           if len(sans_rel(t.encodage, voc).input_ids) <= T_MAX]  # fmt: skip
            print(f"{src} : {len(tirages)} exemples", flush=True)
            for k in range(0, len(tirages), 64):
                lot = tirages[k : k + 64]
                items = [(t.exemple, Contexte.depuis_exemple(t.exemple, t.valeurs, neg))
                         for t in lot]  # fmt: skip
                for t, s in zip(lot, dec.suites(items), strict=True):
                    r = mesure(t, s) | ({"hors_limite": True} if s == ["HORS_LIMITE"] else {})
                    rs.append(r)
                    fs.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(
                    f"{src} {k + len(lot)}/{len(tirages)} ; F1 moyen "
                    f"{bilan([r for r in rs if r['source'] == src])['f1']}",
                    flush=True,
                )
    par = defaultdict(lambda: defaultdict(list))
    for r in rs:
        par[r["source"]]["total"].append(r)
        par[r["source"]][r["genre"]].append(r)
        if (a1 or b) and not r.get("hors_limite"):
            par[r["source"]]["dans_limite"].append(r)
    res = {"point_de_controle": str(chemin), "pas": pas, "n": len(rs), "variante": variante,
           "corrige": corrige,
           "hors_limite": sum(bool(r.get("hors_limite")) for r in rs),
           "secondes": time.time() - t0,
           "sources": {s: {g: bilan(x) for g, x in gs.items()}
                       for s, gs in par.items()}}  # fmt: skip
    (sortie / "resultats.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    texte = rapport(f"{chemin.parent.name}/{chemin.name} (pas {pas})", res, variante)
    (sortie / "rapport.md").write_text(texte, encoding="utf-8")
    return res


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    corrige = "corrige" in a
    a = [x for x in a if x != "corrige"]
    chemin = Path(a[0]) if a else sorted(sorted(Path("runs").glob("*-a0"))[-1].glob("pas-*.pt"))[-1]
    evaluer(chemin, *map(int, a[1:3]), *a[3:4], corrige=corrige)
    sortie = f"eval-{chemin.stem}{'-corrige' if corrige else ''}"
    print((chemin.parent / sortie / "rapport.md").read_text(encoding="utf-8"))
