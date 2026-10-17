"""Écriture du corpus synthétique niveau 0 (SPEC.md §12).

Arborescence : `<sortie>/<partie>/<dossier>/P01.pdf …`, `verite.json` (monde, pièces
gardées, lignes et faits déclarés, conflit) et `questions.json` (questions, vérité terrain
et synthèses, `questions.py`). Une pièce qui échoue au contrôle de provenance n'est pas
écrite. `<sortie>/controle.json` compte pièces, rejets, questions et erreurs.
La vérité terrain contient les noms : elle reste dans `runs/`, hors de git, et n'est
pas un fichier d'entraînement (les exemples passeront par l'anonymiseur).
"""

import json
import shutil
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ccm.config import WorldgenConfig
from ccm.data.worldgen.controle import controler_pdf, controler_piece
from ccm.data.worldgen.monde import generer_monde
from ccm.data.worldgen.pdf import rendre_pdf
from ccm.data.worldgen.pieces import Dossier, rediger_dossier
from ccm.data.worldgen.questions import controler_questions, poser_questions


def produire_dossier(
    graine: int, reservoir: str, cfg: WorldgenConfig, exclus: frozenset[str]
) -> tuple[Dossier, dict[str, bytes], list[str]]:
    """Dossier contrôlé : (dossier aux pièces gardées, PDF par pièce, erreurs)."""
    d = rediger_dossier(generer_monde(graine, reservoir, cfg, exclus), cfg)
    pdfs, erreurs, gardees = {}, [], []
    for piece in d.pieces:
        pdf = rendre_pdf(piece, cfg.redaction.pdf)
        e = controler_piece(d, piece) + controler_pdf(pdf, piece)
        if e:
            erreurs += [f"{d.id}/{x}" for x in e]
        else:
            pdfs[piece.id] = pdf
            gardees.append(piece)
    return d.model_copy(update=dict(pieces=tuple(gardees))), pdfs, erreurs


def _ecrire(args) -> dict:
    graine, reservoir, cfg, exclus, dossier_dir = args
    d, pdfs, erreurs = produire_dossier(graine, reservoir, cfg, exclus)
    dossier_dir = Path(dossier_dir) / d.id
    if dossier_dir.exists():
        shutil.rmtree(dossier_dir)
    dossier_dir.mkdir(parents=True)
    for pid, pdf in pdfs.items():
        (dossier_dir / f"{pid}.pdf").write_bytes(pdf)
    (dossier_dir / "verite.json").write_text(d.model_dump_json(indent=1), encoding="utf-8")
    qs = poser_questions(d, cfg)
    texte = json.dumps([q.model_dump(mode="json") for q in qs], ensure_ascii=False, indent=1)
    (dossier_dir / "questions.json").write_text(texte, encoding="utf-8")
    types = Counter(p.type for p in d.pieces)
    return dict(
        pieces=len(d.pieces) + len({x.split(" ")[0] for x in erreurs}),
        rejetees=len({x.split(" ")[0] for x in erreurs}),
        lignes=sum(len(p.lignes) for p in d.pieces),
        faits=sum(len(x.faits) for p in d.pieces for x in p.lignes),
        conflit=d.conflit is not None,
        types=dict(types),
        erreurs=erreurs,
        questions=Counter(f"{q.type}/{q.sous_type}" for q in qs),
        formulations={(ph.relation, ph.gabarit) for q in qs for ph in q.synthese},
        erreurs_questions=controler_questions(d, qs),
    )


def ecrire_corpus(
    cfg: WorldgenConfig,
    exclus: frozenset[str],
    sortie: Path,
    parties: list[str] | None = None,
    limite: int | None = None,
    processus: int | None = None,
) -> dict:
    taches = []
    for nom, partie in cfg.corpus.items():
        if parties and nom not in parties:
            continue
        n = partie.dossiers if limite is None else min(limite, partie.dossiers)
        for i in range(n):
            taches.append((nom, (partie.graine + i, partie.reservoir, cfg, exclus, sortie / nom)))
    bilan: dict = {}
    with ProcessPoolExecutor(processus) as ex:
        resultats = ex.map(_ecrire, [t for _, t in taches], chunksize=8)
        for (nom, _), r in zip(taches, resultats, strict=True):
            b = bilan.setdefault(
                nom, dict(dossiers=0, pieces=0, rejetees=0, lignes=0, faits=0, conflits=0)
            )
            b["dossiers"] += 1
            b["conflits"] += r["conflit"]
            for k in ("pieces", "rejetees", "lignes", "faits"):
                b[k] += r[k]
            b.setdefault("types", Counter()).update(r["types"])
            b.setdefault("erreurs", []).extend(r["erreurs"])
            b.setdefault("questions", Counter()).update(r["questions"])
            b.setdefault("formulations", set()).update(r["formulations"])
            b.setdefault("erreurs_questions", []).extend(r["erreurs_questions"])
    for b in bilan.values():
        b["types"] = dict(sorted(b["types"].items()))
        b["questions"] = dict(sorted(b["questions"].items()))
        b["formulations"] = dict(sorted(Counter(rel for rel, _ in b["formulations"]).items()))
    sortie.mkdir(parents=True, exist_ok=True)
    (sortie / "controle.json").write_text(
        json.dumps(bilan, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )
    return bilan
