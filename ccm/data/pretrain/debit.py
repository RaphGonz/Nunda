"""Débit des détecteurs et décision GLiNER (SPEC.md §12, « Coût de la détection »).

Échantillon tiré de `brut` (7 M jetons fr, 3 M en par défaut), coupé en phrases comme la
chaîne. Chaque détecteur est mesuré seul, en jetons par seconde, après un tour de chauffe
(chargement du modèle). Extrapolation au corpus (`jetons_total`, parts des langues des
quotas). Règle de Raphael : GLiNER sur tout le corpus s'il y tient en `heures_max` heures de
GPU (5 nuits de 8 h), sinon sur `part` du corpus, tiré par document.
"""

import time
from collections.abc import Callable

from ccm.config import CorpusConfig
from ccm.data.pretrain.etat import lire_lignes, tirage
from ccm.data.pretrain.fenetres import Compteur, decouper_document
from ccm.data.pretrain.nettoyer import nettoyer

Mesure = Callable[[list[str]], object]  # textes → résultat ignoré


def echantillon(paquets, cfg: CorpusConfig, compter: Compteur) -> dict[str, list[str]]:
    """Phrases de documents gardés, tirés par graine sur l'id (un sur cinq), dans l'ordre des
    paquets (déjà mélangés entre sources), jusqu'aux jetons voulus."""
    voulus = dict(cfg.debit.jetons)
    pris = dict.fromkeys(voulus, 0)
    out: dict[str, list[str]] = {lg: [] for lg in voulus}
    docs = (
        d for p in paquets for d in lire_lignes(p) if tirage(cfg.graine, "debit", d["id"]) < 0.2
    )
    for d in docs:
        if all(pris[lg] >= voulus[lg] for lg in voulus):
            break
        lg = d["langue"]
        if lg not in voulus or pris[lg] >= voulus[lg]:
            continue
        texte, raison = nettoyer(d["texte"], cfg.sources[d["source"]], cfg.nettoyage)
        if raison:
            continue
        phr, fen = decouper_document(texte, lg, compter, cfg.jetons_fenetre - cfg.reserve_canari)
        out[lg] += [texte[a:b] for a, b in phr]
        pris[lg] += sum(j for _, _, j in fen)
    return out


def mesurer(detecteurs: dict[str, dict[str, Mesure]], phrases: dict[str, list[str]],
            cfg: CorpusConfig, compter: Compteur, chauffe: int = 64) -> dict:  # fmt: skip
    """`detecteurs[langue][nom]` ; rend les débits, l'extrapolation et la décision."""
    quotas = {lg: sum(s.quota for s in cfg.sources.values() if s.langue == lg) for lg in phrases}
    total_quotas = sum(quotas.values()) or 1
    out: dict = {"langues": {}, "jetons_total": cfg.jetons_total}
    heures_gliner = 0.0
    for lg, ts in phrases.items():
        jetons = sum(compter(ts))
        corpus = cfg.jetons_total * quotas[lg] / total_quotas
        res = {"phrases": len(ts), "jetons": jetons, "jetons_corpus": corpus, "detecteurs": {}}
        for nom, f in detecteurs.get(lg, {}).items():
            f(ts[:chauffe])
            t0 = time.perf_counter()
            f(ts)
            s = max(time.perf_counter() - t0, 1e-9)
            heures = corpus / (jetons / s) / 3600 if jetons else 0.0
            res["detecteurs"][nom] = {"secondes": s, "jetons_par_s": jetons / s,
                                      "heures_corpus": heures}  # fmt: skip
            if nom == "gliner":
                heures_gliner += heures
        out["langues"][lg] = res
    out["heures_gliner"] = heures_gliner
    out["heures_max"] = cfg.gliner.heures_max
    out["gliner"] = "tout" if heures_gliner <= cfg.gliner.heures_max else "10pct"
    return out


def detecteurs(icfg, dcfg) -> dict[str, dict[str, Mesure]]:
    """Chaque détecteur seul, par langue (chaînes de `chaine.detections`), plus les nombres."""
    from ccm.data.publics import nombres_en
    from ccm.ingest.numbers import nombres
    from ccm.ner.detectors import d1_gliner, d2_spacy, d3_regles, d4_majuscules

    det = icfg.detection
    gliner = det.gliner.model_copy(update={"lot": dcfg.lot_gliner})
    tous = {
        "gliner": lambda ts: d1_gliner(ts, gliner),
        "spacy": lambda ts: d2_spacy(ts, det.spacy),
        "regle": lambda ts: [d3_regles(t, det, icfg.nombres) for t in ts],
        "majuscules": lambda ts: [d4_majuscules(t, det) for t in ts],
    }
    n = icfg.nombres
    return {
        "fr": {d: tous[d] for d in det.detecteurs}
        | {"nombres": lambda ts: [nombres(t, n) for t in ts]},
        "en": {d: tous[d] for d in dcfg.detecteurs_en}
        | {"nombres": lambda ts: [nombres_en(t, (), n.annee_min, n.annee_max) for t in ts]},
    }
