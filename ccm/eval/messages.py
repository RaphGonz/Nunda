"""Mesure : noms des messages de l'utilisateur (SPEC.md §6), trois variantes de la
recherche sans casse des noms connus de la base.

- V0 : les normes connues entières (ancienne règle) ;
- V1 : V0, plus les noms de famille des mentions PER de la base ;
- V2 : V0, plus chaque mot d'au moins 3 lettres des normes connues, sauf titres,
  particules, mots vides et mots courants des lexiques de D4 (règle actuelle,
  `ner.propagate.detecter_message`).

Deux conditions : les messages tels qu'écrits par le générateur (« ecrit »), et les mêmes
messages dont chaque nom est réécrit en minuscules sans accents (« minuscules », ce que
tape souvent un utilisateur). Chaque dossier est ingéré avec la vraie chaîne. Une mention
de référence est masquée si chacun de ses mots est dans une zone (comme `eval/noms.py`).
Une zone qui ne touche aucun nom de référence est un faux positif.

    uv run python -m ccm.eval.messages runs/corpus/niveau0/validation runs/messages/validation
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from ccm.anonymize.names import nom_famille
from ccm.config import IngestConfig, load_config
from ccm.data.worldgen.questions import Question, Tour
from ccm.ingest.pipeline import fichiers_pdf, ingerer_fichiers
from ccm.ingest.racines import sans_accents
from ccm.ner.propagate import chercher_connus, connus, mots_connus
from ccm.ner.union import detecter, unir
from ccm.schema import TypeNom, ouvrir_stock

TYPES = ("PER", "ORG", "LIEU", "REF")
VARIANTES = ("V0", "V1", "V2")
CONDITIONS = ("ecrit", "minuscules")
_MOT = re.compile(r"\w+")


def chaines(con, cfg: IngestConfig, variante: str) -> dict[str, TypeNom]:
    types = connus(con, cfg)
    extra: dict[str, TypeNom] = {}
    if variante == "V1":
        for (s,) in con.execute("SELECT DISTINCT surface FROM mention WHERE type = 'PER'"):
            f = nom_famille(s, cfg.noms)
            if f and len(f) >= 3:
                extra[f] = TypeNom.PER
    if variante == "V2":
        extra = mots_connus(con, cfg, types)
    return {**extra, **types}


def _minuscules(t: Tour) -> Tour:
    """Chaque nom réécrit en minuscules sans accents ; positions recalculées."""
    texte, faits, k, decalage = "", [], 0, 0
    for f in sorted(t.faits, key=lambda f: f.debut):
        s = sans_accents(f.surface).lower() if f.genre in TYPES else f.surface
        texte += t.texte[k : f.debut] + s
        d = f.debut + decalage
        faits.append(f.model_copy(update=dict(debut=d, fin=d + len(s), surface=s)))
        decalage += len(s) - (f.fin - f.debut)
        k = f.fin
    return t.model_copy(update=dict(texte=texte + t.texte[k:], faits=tuple(faits)))


def _couvre(zones, d: int, f: int) -> bool:
    return any(z.debut <= d and f <= z.fin for z in zones)


def mesurer_dossier(dossier: Path, sortie: Path, cfg: IngestConfig) -> dict:
    stock = sortie / f"{dossier.name}.sqlite"
    if not stock.exists():
        con = ouvrir_stock(stock)
        ingerer_fichiers(con, fichiers_pdf([dossier]), cfg)
        con.commit()
    else:
        con = ouvrir_stock(stock)
    qs = json.loads((dossier / "questions.json").read_text(encoding="utf-8"))
    tours = [
        t
        for q in qs
        for t in (Question.model_validate(q).message, *Question.model_validate(q).historique)
        if t.role == "UTILISATEUR"
    ]
    cherche = {v: chaines(con, cfg, v) for v in VARIANTES}
    con.close()

    n: Counter = Counter()
    exemples: dict[str, list] = {}
    for c in CONDITIONS:
        msgs = tours if c == "ecrit" else [_minuscules(t) for t in tours]
        detectees = detecter([t.texte for t in msgs], cfg)
        for v in VARIANTES:
            cle = f"{c}|{v}"
            for t, zs in zip(msgs, detectees, strict=True):
                zs = unir(zs + chercher_connus(t.texte, cherche[v], zs))
                refs = [f for f in t.faits if f.genre in TYPES]
                fuite = False
                for f in refs:
                    mots = [m.span() for m in _MOT.finditer(t.texte, f.debut, f.fin)]
                    n[f"{cle}|{f.genre}|ref"] += 1
                    if all(_couvre(zs, a, b) for a, b in mots):
                        n[f"{cle}|{f.genre}|masquee"] += 1
                    else:
                        fuite = True
                        exemples.setdefault(f"{cle}|manques", []).append(f.surface)
                n[f"{cle}|messages"] += 1
                n[f"{cle}|fuites"] += fuite
                for z in zs:
                    n[f"{cle}|zones"] += 1
                    if not any(z.debut < f.fin and f.debut < z.fin for f in refs):
                        n[f"{cle}|faux"] += 1
                        exemples.setdefault(f"{cle}|faux", []).append(t.texte[z.debut : z.fin])
                for f in t.faits:
                    if f.genre in ("NUM", "DATE", "HEURE"):
                        n[f"{cle}|nombres"] += 1
                        n[f"{cle}|nombres_masques"] += any(
                            z.debut < f.fin and f.debut < z.fin for z in zs
                        )
    return dict(dossier=dossier.name, compte=dict(n), exemples=exemples)


def _bilan(rs: list[dict]) -> dict:
    n: Counter = Counter()
    ex: dict[str, Counter] = {}
    for r in rs:
        n.update(r["compte"])
        for k, xs in r["exemples"].items():
            ex.setdefault(k, Counter()).update(xs)
    out = {}
    for c in CONDITIONS:
        for v in VARIANTES:
            k = f"{c}|{v}"
            out[k] = dict(
                rappel={
                    t: round(n[f"{k}|{t}|masquee"] / n[f"{k}|{t}|ref"], 4)
                    for t in TYPES
                    if n[f"{k}|{t}|ref"]
                },
                messages=n[f"{k}|messages"],
                messages_avec_fuite=n[f"{k}|fuites"],
                zones=n[f"{k}|zones"],
                faux_positifs=n[f"{k}|faux"],
                nombres_masques=f"{n[f'{k}|nombres_masques']} / {n[f'{k}|nombres']}",
                manques_frequents=ex.get(f"{k}|manques", Counter()).most_common(15),
                faux_frequents=ex.get(f"{k}|faux", Counter()).most_common(15),
            )
    return out


def main(source: Path, sortie: Path, tranche: slice = slice(None)) -> dict:
    sortie.mkdir(parents=True, exist_ok=True)
    cfg = load_config("ingest")
    dossiers = sorted(p for p in source.iterdir() if (p / "verite.json").exists())[tranche]
    rs = [mesurer_dossier(d, sortie, cfg) for d in dossiers]
    bilan = _bilan(rs)
    (sortie / "bilan.json").write_text(
        json.dumps(dict(bilan=bilan, dossiers=rs), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return bilan


if __name__ == "__main__":
    t = [int(x) if x else None for x in sys.argv[3].split(":")] if len(sys.argv) > 3 else []
    tranche = slice(*t) if len(t) == 2 else slice(t[0] if t else None)
    print(
        json.dumps(
            main(Path(sys.argv[1]), Path(sys.argv[2]), tranche), ensure_ascii=False, indent=1
        )
    )
