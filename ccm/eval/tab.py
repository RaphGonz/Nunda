"""Mesure de la détection des noms sur TAB, partie `dev` (SPEC.md §6, §12) : quelle chaîne
pour l'anglais, et pour un texte en minuscules (FinQA).

Une mention annotée (tout annotateur, identifiant direct ou quasi) est masquée si chacun de
ses mots est dans une zone détectée, comme dans `eval.noms`. Sont aussi comptés : la part des
caractères masqués, et la part des caractères masqués hors de toute mention annotée.

    uv run python -m ccm.eval.tab D:/Nunda-donnees/brut runs/tab/mesure.json
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from ccm.config import IngestConfig, load_config
from ccm.data import finqa
from ccm.data.publics import detecter_minuscules, phrases
from ccm.ner.union import detecter

_MOT = re.compile(r"\w+")
_TYPES = ("PERSON", "ORG", "LOC", "CODE", "DEM", "DATETIME", "QUANTITY", "MISC")


def _variante(cfg: IngestConfig, detecteurs: tuple[str, ...]) -> IngestConfig:
    return cfg.model_copy(
        update={"detection": cfg.detection.model_copy(update={"detecteurs": detecteurs})}
    )


def _morceaux(texte: str) -> list[tuple[int, str]]:
    """(position dans le document, phrase)."""
    out, pos = [], 0
    for ligne in texte.split("\n"):
        if ligne.strip():
            out += [(pos + d, p) for d, p in phrases(ligne, "en")]
        pos += len(ligne) + 1
    return out


def mesurer(docs: list[dict], detection, minuscules: bool) -> dict:
    """`detection(textes)` → zones de chaque texte."""
    lus = [(i, d, p) for i, doc in enumerate(docs) for d, p in _morceaux(doc["text"])]
    zones = detection([p.lower() if minuscules else p for _, _, p in lus])
    masques = [bytearray(len(doc["text"])) for doc in docs]
    for (i, d, _), zs in zip(lus, zones, strict=True):
        for z in zs:
            masques[i][d + z.debut : d + z.fin] = b"\1" * (z.fin - z.debut)
    vus, masquees = Counter(), Counter()
    total = masque = hors = 0
    for doc, m in zip(docs, masques, strict=True):
        annote = bytearray(len(doc["text"]))
        mentions = {
            (e["start_offset"], e["end_offset"], e["entity_type"])
            for a in doc["annotations"].values()
            for e in a["entity_mentions"]
            if e["identifier_type"] != "NO_MASK"
        }
        for d, f, _ in mentions:
            annote[d:f] = b"\1" * (f - d)
        for d, f, t in mentions:
            mots = list(_MOT.finditer(doc["text"][d:f]))
            vus[t] += 1
            masquees[t] += all(all(m[d + x.start() : d + x.end()]) for x in mots)
        for c, a, b in zip(doc["text"], m, annote, strict=True):
            if not c.isspace():
                total += 1
                masque += a
                hors += a and not b
    return {
        "rappel": {t: round(masquees[t] / vus[t], 4) for t in _TYPES if vus[t]},
        "mentions": {t: vus[t] for t in _TYPES if vus[t]},
        "caracteres_masques": round(masque / total, 4),
        "masques_hors_mentions": round(hors / max(masque, 1), 4),
    }


def main(brut: Path, sortie: Path) -> None:
    cfg = load_config("ingest")
    lot = load_config("donnees").lot_gliner
    gliner = cfg.detection.gliner.model_copy(update={"lot": lot})
    cfg = cfg.model_copy(update={"detection": cfg.detection.model_copy(update={"gliner": gliner})})
    docs = json.loads((brut / "tab" / "echr_dev.json").read_text(encoding="utf-8"))
    bilan = {}
    for nom, det in (
        ("quatre detecteurs", cfg.detection.detecteurs),
        ("gliner+regle", ("gliner", "regle")),
        ("gliner+regle+majuscules", ("gliner", "regle", "majuscules")),
    ):
        c = _variante(cfg, det)
        bilan[nom] = mesurer(docs, lambda ts, c=c: detecter(ts, c), False)
        print(nom, json.dumps(bilan[nom]), flush=True)
    bruts, _ = finqa.lire(brut / "finqa" / "dev.json")
    textes = sorted({t for b in bruts for par in b.paragraphes for t in par})
    for seuil in (0.6, 0.3):
        nom = f"minuscules seuil {seuil}"
        bilan[nom] = mesurer(docs, lambda ts, s=seuil: detecter_minuscules(ts, cfg, s), True)
        zs = detecter_minuscules(textes, cfg, seuil)
        total = sum(len(t) for t in textes)
        bilan[nom]["finqa_caracteres_masques"] = round(
            sum(z.fin - z.debut for x in zs for z in x) / total, 4
        )
        print(nom, json.dumps(bilan[nom]), flush=True)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(bilan, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
