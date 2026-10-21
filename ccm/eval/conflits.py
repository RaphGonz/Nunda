"""Mesure de l'étape 8 (conflits, SPEC.md §5 et §14) sur le corpus synthétique.

Chaque dossier est ingéré dans un stock neuf. La vérité terrain d'un dossier à versions
contradictoires donne les paires de référence : une ligne de l'événement en conflit dans
la version du monde et une ligne dans la version contradictoire, qui portent toutes deux
le champ changé (heure, montant ou personne) avec des valeurs différentes (même règle
que le contrôle des questions CONFLIT). Toute autre arête CONFLIT est un faux positif.

L'étape 5 (noms) n'existe pas encore : la mesure est faite deux fois, sans mentions
(table `mention` vide, comme à l'ingestion d'aujourd'hui) et avec les mentions de
référence (faits PER, ORG, LIEU, REF de la vérité, norme de SPEC.md §6 ; nombres lus dans
une mention retirés, comme le fera l'exclusion de l'étape 6).

    uv run python -m ccm.eval.conflits runs/corpus/niveau0/validation runs/conflits/validation
"""

import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ccm.anonymize.names import norme
from ccm.config import load_config
from ccm.data.worldgen.pieces import Dossier
from ccm.graph.store import ajouter_mentions
from ccm.ingest.conflicts import detecter_conflits
from ccm.ingest.pipeline import fichiers_pdf, ingerer_fichiers
from ccm.schema import ouvrir_stock

GENRE_CHAMP = {"HEURE": "HEURE", "MONTANT": "NUM", "PERSONNE": "PER"}
TYPES_NOMS = ("PER", "ORG", "LIEU", "REF")


def _lignes_props(con, d: Dossier) -> dict[tuple[str, int], int]:
    """(pièce, indice de ligne) → prop_id, par texte exact, dans l'ordre."""
    out = {}
    for p in d.pieces:
        props = con.execute(
            "SELECT prop_id, texte FROM proposition WHERE piece_id = ? OR piece_id LIKE ? "
            "ORDER BY prop_id",
            (p.id, f"{p.id}.%"),
        ).fetchall()
        k = 0
        for i, ligne in enumerate(p.lignes):
            j = next((j for j in range(k, len(props)) if props[j][1] == ligne.texte), None)
            if j is not None:
                out[(p.id, i)] = props[j][0]
                k = j + 1
    return out


def _reference(d: Dossier, props: dict) -> set[frozenset]:
    if d.conflit is None:
        return set()
    g, e = GENRE_CHAMP[d.conflit.champ], d.conflit.evenement
    cotes: dict[int, list] = {0: [], 1: []}
    for p in d.pieces:
        for i, ligne in enumerate(p.lignes):
            vals = {f.valeur or f.entite for f in ligne.faits if f.genre == g}
            if ligne.evenement == e and vals and (p.id, i) in props:
                cotes[ligne.version].append((props[(p.id, i)], vals))
    return {frozenset((a, b)) for a, va in cotes[0] for b, vb in cotes[1] if va != vb}


def _predites(con) -> set[frozenset]:
    return {frozenset(r) for r in con.execute("SELECT src, dst FROM arete WHERE type = 'CONFLIT'")}


def mesurer_dossier(dossier: Path, sortie: Path) -> dict:
    cfg = load_config("ingest")
    d = Dossier.model_validate_json((dossier / "verite.json").read_text(encoding="utf-8"))
    stock = sortie / f"{dossier.name}.sqlite"
    stock.unlink(missing_ok=True)
    con = ouvrir_stock(stock)
    ingerer_fichiers(con, fichiers_pdf([dossier]), cfg)
    props = _lignes_props(con, d)
    ref = _reference(d, props)
    sans = _predites(con)

    for p in d.pieces:
        for i, ligne in enumerate(p.lignes):
            pid = props.get((p.id, i))
            ms = [f for f in ligne.faits if f.genre in TYPES_NOMS]
            if pid is None or not ms:
                continue
            ajouter_mentions(
                con,
                pid,
                [
                    (f.debut, f.fin, f.surface, norme(f.surface, cfg.noms), f.genre, "reference")
                    for f in ms
                ],
            )
            for f in ms:
                con.execute(
                    "DELETE FROM nombre WHERE prop_id = ? AND debut < ? AND fin > ?",
                    (pid, f.fin, f.debut),
                )
    detecter_conflits(con, cfg)
    con.commit()
    avec = _predites(con)
    textes = dict(con.execute("SELECT prop_id, texte FROM proposition"))
    con.close()

    def bilan(pred):
        return dict(
            vp=len(pred & ref),
            fp=len(pred - ref),
            fn=len(ref - pred),
            faux=[sorted(textes[x] for x in p) for p in pred - ref],
            manques=[sorted(textes[x] for x in p) for p in ref - pred],
        )

    return dict(
        dossier=dossier.name,
        champ=d.conflit.champ if d.conflit else None,
        lignes=sum(len(p.lignes) for p in d.pieces),
        retrouvees=len(props),
        sans_mentions=bilan(sans),
        mentions_reference=bilan(avec),
    )


def _scores(rs: list[dict], cle: str) -> dict:
    vp, fp, fn = (sum(r[cle][k] for r in rs) for k in ("vp", "fp", "fn"))
    par_champ = Counter()
    for r in rs:
        if r["champ"]:
            par_champ[(r["champ"], "vp")] += r[cle]["vp"]
            par_champ[(r["champ"], "ref")] += r[cle]["vp"] + r[cle]["fn"]
    return dict(
        vp=vp,
        fp=fp,
        fn=fn,
        precision=round(vp / (vp + fp), 4) if vp + fp else None,
        rappel=round(vp / (vp + fn), 4) if vp + fn else None,
        rappel_par_champ={
            c: f"{par_champ[(c, 'vp')]} / {par_champ[(c, 'ref')]}" for c in GENRE_CHAMP
        },
    )


def main(source: Path, sortie: Path, processus: int = 8) -> dict:
    sortie.mkdir(parents=True, exist_ok=True)
    dossiers = sorted(p for p in source.iterdir() if (p / "verite.json").exists())
    with ProcessPoolExecutor(processus) as ex:
        rs = list(ex.map(mesurer_dossier, dossiers, [sortie] * len(dossiers)))
    bilan = dict(
        dossiers=len(rs),
        a_conflit=sum(r["champ"] is not None for r in rs),
        lignes=sum(r["lignes"] for r in rs),
        retrouvees=sum(r["retrouvees"] for r in rs),
        sans_mentions=_scores(rs, "sans_mentions"),
        mentions_reference=_scores(rs, "mentions_reference"),
    )
    (sortie / "bilan.json").write_text(
        json.dumps(dict(bilan=bilan, dossiers=rs), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return bilan


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False, indent=1))
