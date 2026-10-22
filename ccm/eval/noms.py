"""Mesure de l'étape 5 (détection des noms, SPEC.md §6 et §14) sur le corpus synthétique.

Chaque dossier est ingéré dans un stock neuf, avec la vraie chaîne (détecteurs, union,
limites, propagation). Les mentions de référence sont les faits PER, ORG, LIEU et REF de
la vérité, à leurs positions dans la ligne (le texte de la ligne est celui de la
proposition). Pour chaque type :

- masquée : chaque mot de la mention est dans une zone détectée, de tout type (la
  ponctuation et les blancs ne révèlent rien) ; c'est le rappel du seuil de phase 2 ;
- exacte : une zone détectée a les mêmes limites ;
- bien typée : masquée, et la zone qui couvre son premier mot a le type de référence.

Sont aussi comptés : les zones détectées qui ne touchent aucune mention de référence
(faux positifs, par type) et les nombres de référence (NUM, DATE, HEURE) recouverts par
une zone de nom (perdus pour l'étape 6).

    uv run python -m ccm.eval.noms runs/corpus/niveau0/validation runs/noms/validation
"""

import json
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ccm.config import load_config
from ccm.data.worldgen.pieces import Dossier
from ccm.eval.conflits import _lignes_props
from ccm.ingest.pipeline import fichiers_pdf, ingerer_fichiers
from ccm.schema import ouvrir_stock

TYPES = ("PER", "ORG", "LIEU", "REF")
NOMBRES = ("NUM", "DATE", "HEURE")
_MOT = re.compile(r"\w+")


def _couvre(zones, d: int, f: int) -> bool:
    return any(z[0] <= d and f <= z[1] for z in zones)


def mesurer_dossier(dossier: Path, sortie: Path) -> dict:
    cfg = load_config("ingest")
    d = Dossier.model_validate_json((dossier / "verite.json").read_text(encoding="utf-8"))
    stock = sortie / f"{dossier.name}.sqlite"
    stock.unlink(missing_ok=True)
    con = ouvrir_stock(stock)
    ingerer_fichiers(con, fichiers_pdf([dossier]), cfg)
    props = _lignes_props(con, d)
    zones: dict[int, list] = {}
    for p, a, b, t in con.execute("SELECT prop_id, debut, fin, type FROM mention"):
        zones.setdefault(p, []).append((a, b, t))
    con.close()

    n = Counter()
    manques, faux = [], []
    for piece in d.pieces:
        for i, ligne in enumerate(piece.lignes):
            pid = props.get((piece.id, i))
            if pid is None:
                n["lignes_perdues"] += 1
                continue
            zs = zones.get(pid, [])
            refs = [f for f in ligne.faits if f.genre in TYPES]
            for f in refs:
                mots = [m.span() for m in _MOT.finditer(ligne.texte, f.debut, f.fin)]
                n[(f.genre, "ref")] += 1
                if all(_couvre(zs, a, b) for a, b in mots):
                    n[(f.genre, "masquee")] += 1
                    premier = next(z for z in zs if z[0] <= mots[0][0] and mots[0][1] <= z[1])
                    n[(f.genre, "bien_typee")] += premier[2] == f.genre
                else:
                    manques.append([f.genre, f.surface, ligne.texte])
                n[(f.genre, "exacte")] += any(z[0] == f.debut and z[1] == f.fin for z in zs)
            for z in zs:
                n["zones"] += 1
                if not any(z[0] < f.fin and f.debut < z[1] for f in refs):
                    n[(z[2], "faux")] += 1
                    faux.append([z[2], ligne.texte[z[0] : z[1]]])
            for f in ligne.faits:
                if f.genre in NOMBRES:
                    n["nombres"] += 1
                    n["nombres_masques"] += any(z[0] < f.fin and f.debut < z[1] for z in zs)
    return dict(
        dossier=dossier.name,
        compte={"|".join(k) if isinstance(k, tuple) else k: v for k, v in n.items()},
        manques=manques,
        faux=faux,
    )


def _bilan(rs: list[dict]) -> dict:
    n = Counter()
    for r in rs:
        n.update(r["compte"])

    def taux(a, b):
        return round(n[a] / n[b], 4) if n[b] else None

    par_type = {
        t: dict(
            mentions=n[f"{t}|ref"],
            rappel=taux(f"{t}|masquee", f"{t}|ref"),
            exactes=taux(f"{t}|exacte", f"{t}|ref"),
            bien_typees=taux(f"{t}|bien_typee", f"{t}|ref"),
        )
        for t in TYPES
    }
    tous = sum(n[f"{t}|ref"] for t in TYPES)
    return dict(
        dossiers=len(rs),
        lignes_perdues=n["lignes_perdues"],
        rappel_tous_types=round(sum(n[f"{t}|masquee"] for t in TYPES) / max(1, tous), 4),
        par_type=par_type,
        zones=n["zones"],
        faux_positifs={t: n[f"{t}|faux"] for t in (*TYPES, "AUTRE")},
        precision_zones=round(1 - sum(n[f"{t}|faux"] for t in (*TYPES, "AUTRE")) / n["zones"], 4)
        if n["zones"]
        else None,
        nombres_masques=f"{n['nombres_masques']} / {n['nombres']}",
        manques_frequents=Counter(f"{g} {s}" for r in rs for g, s, _ in r["manques"]).most_common(
            30
        ),
        faux_frequents=Counter(f"{g} {s}" for r in rs for g, s in r["faux"]).most_common(30),
    )


def main(source: Path, sortie: Path, tranche: slice = slice(None), processus: int = 3) -> dict:
    sortie.mkdir(parents=True, exist_ok=True)
    dossiers = sorted(p for p in source.iterdir() if (p / "verite.json").exists())[tranche]
    with ProcessPoolExecutor(processus) as ex:
        rs = list(ex.map(mesurer_dossier, dossiers, [sortie] * len(dossiers)))
    bilan = _bilan(rs)
    (sortie / "bilan.json").write_text(
        json.dumps(dict(bilan=bilan, dossiers=rs), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return bilan


if __name__ == "__main__":
    # Tranche des dossiers : « 20 » (les 20 premiers) ou « 20:60 ».
    t = [int(x) if x else None for x in sys.argv[3].split(":")] if len(sys.argv) > 3 else []
    tranche = slice(*t) if len(t) == 2 else slice(t[0] if t else None)
    print(
        json.dumps(
            main(Path(sys.argv[1]), Path(sys.argv[2]), tranche), ensure_ascii=False, indent=1
        )
    )
