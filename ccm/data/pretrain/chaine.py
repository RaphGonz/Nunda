"""Chaîne du corpus de pré-entraînement (SPEC.md §12), reprenable paquet par paquet.

    brut/            documents des sources, mélangés (graine), au quota de chaque source
    brut+canaris/    canaris naturels insérés (§14)
    detecte/         nettoyer, fenêtres, détecter, propager dans le document (passe A)
    occurrences/     occurrences des chaînes candidates dans tout le corpus (passe B)
    final/           liste globale appliquée, remplacer, relations, [P], canaris forcés
    travail/         comptes des chaînes, automates, dédoublonnage : hors du corpus

Chaque paquet s'écrit d'un coup (`.part` puis renommé) et entre dans `etat.json` ; une
relance reprend au premier paquet non fini, et donne les mêmes fichiers, octet pour octet,
qu'une passe d'un coup. Les détecteurs, seule étape sur GPU, tournent dans le processus
principal ; le reste dans `processus` processus fils. La détection est gardée en cache par
paquet (`remplir_cache`, clé SHA-1 de la phrase) : une relance ne refait que le manquant.
"""

import json
import multiprocessing
import random
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa

from ccm.config import CorpusConfig, IngestConfig, SourcePretrain
from ccm.data import canaries
from ccm.data.pretrain import propager as prop
from ccm.data.pretrain.etat import Etape, ecrire_table, lire_lignes, tirage
from ccm.data.pretrain.fenetres import compteur, decouper_document
from ccm.data.pretrain.nettoyer import empreinte, nettoyer
from ccm.data.pretrain.remplacer import marquer_fenetre
from ccm.data.publics import _cle, phrases, remplir_cache
from ccm.data.publics import _zones as zones_json
from ccm.ner.detectors import Zone
from ccm.ner.propagate import propager
from ccm.schema import TypeNom

Detection = Callable[[list[str]], list[list[Zone]]]

_CHAINES = ("fr", "fr_sans_gliner", "en", "en_sans_gliner")
_S = pa.string()
SCHEMA_BRUT = pa.schema([("id", _S), ("source", _S), ("langue", _S), ("texte", _S)])
SCHEMA_DETECTE = pa.schema([("id", _S), ("source", _S), ("langue", _S), ("texte", _S),
                            ("phrases", _S), ("fenetres", _S), ("zones", _S),
                            ("gliner", pa.bool_())])  # fmt: skip
SCHEMA_COMPTES = pa.schema([("chaine", _S), ("rang", pa.int64()), ("detectees", pa.int64()),
                            ("documents", pa.int64())])  # fmt: skip
SCHEMA_OCCURRENCES = pa.schema([("chaine", _S), ("occurrences", pa.int64())])
SCHEMA_FINAL = pa.schema([("id", _S), ("document", _S), ("source", _S), ("langue", _S),
                          ("texte", _S), ("marques", _S), ("noms", pa.int64()), ("nn", _S),
                          ("n_props", pa.int64()), ("a_p", pa.bool_()),
                          ("jetons", pa.int64())])  # fmt: skip


@dataclass(frozen=True)
class Chemins:
    racine: Path  # racine/pretrain
    canaris: Path  # racine/canaris/canaris.json, hors de `racine`

    def __getattr__(self, etape: str) -> Path:
        return self.racine / {"brut_canaris": "brut+canaris"}.get(etape, etape)


def chemins(racine_donnees: Path, cfg: CorpusConfig) -> Chemins:
    return Chemins(racine_donnees / cfg.sous_dossier, racine_donnees / cfg.canaris)


# --- Processus fils ----------------------------------------------------------------------

_etat: dict = {}


def _init(cfg: CorpusConfig, icfg: IngestConfig) -> None:
    _etat.clear()
    _etat.update(cfg=cfg, icfg=icfg, compter=compteur(cfg.decoupeur), con={})


@contextmanager
def _carte(cfg: CorpusConfig, icfg: IngestConfig):
    """`carte(f, éléments)` : `f` sur chaque élément, dans l'ordre, dans les processus fils."""
    if cfg.processus <= 0:
        _init(cfg, icfg)
        yield lambda f, xs: list(map(f, xs))
        return
    with multiprocessing.Pool(cfg.processus, _init, (cfg, icfg)) as pool:
        yield lambda f, xs: list(pool.imap(f, xs, chunksize=16))


def _cache(chemin: str) -> sqlite3.Connection:
    cons = _etat["con"]
    if chemin not in cons:
        for c in cons.values():
            c.close()
        cons.clear()
        cons[chemin] = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    return cons[chemin]


def _zones_de(chemin: str, textes: list[str]) -> list[list[Zone]]:
    con = _cache(chemin)
    out = []
    for t in textes:
        (v,) = con.execute("SELECT valeur FROM zones WHERE cle = ?", (_cle(t),)).fetchone()
        out.append(zones_json(v))
    return out


# --- brut ---------------------------------------------------------------------------------


def melanger(flux: dict[str, Iterator[dict]], quotas: dict[str, int], compter, graine: int
             ) -> Iterator[dict]:  # fmt: skip
    """Documents des sources, tirés au hasard (poids = quota), jusqu'au quota de chacune."""
    rng = random.Random(f"{graine}:melange")
    lus = dict.fromkeys(flux, 0)
    actives = sorted(flux)
    while actives:
        s = rng.choices(actives, weights=[quotas[a] for a in actives])[0]
        doc = next(flux[s], None)
        if doc is None:
            actives.remove(s)
            continue
        lus[s] += compter([doc["texte"]])[0]
        if lus[s] >= quotas[s]:
            actives.remove(s)
        yield doc


def ecrire_brut(docs: Iterable[dict], dossier: Path, par_paquet: int) -> dict:
    """Paquets de `par_paquet` documents ; ceux déjà finis ne sont pas réécrits."""
    etape = Etape(dossier)
    if etape.complet:
        return etape.etat
    n, lot = 0, []

    def vider():
        if not etape.fini(n):
            ecrire_table({k: [d[k] for d in lot] for k in SCHEMA_BRUT.names}, SCHEMA_BRUT,
                         etape.chemin_paquet(n))  # fmt: skip
            etape.finir(
                n, {"documents": len(lot), "sources": dict(Counter(d["source"] for d in lot))}
            )

    for d in docs:
        lot.append(d)
        if len(lot) == par_paquet:
            vider()
            n, lot = n + 1, []
    if lot:
        vider()
    etape.completer()
    return etape.etat


def _paquets(dossier: Path) -> list[tuple[int, Path]]:
    etape = Etape(dossier)
    if not etape.complet:
        raise RuntimeError(f"étape incomplète : {dossier}")
    return [(n, etape.chemin_paquet(n)) for n in etape.paquets()]


# --- canaris naturels ---------------------------------------------------------------------


def _gardable(doc: dict, sources: dict[str, SourcePretrain], cfg: CorpusConfig) -> bool:
    return nettoyer(doc["texte"], sources[doc["source"]], cfg.nettoyage)[1] is None


def _inserer_naturel(texte: str, langue: str, phrase: str, graine: int, id_: str) -> str:
    """Insère la phrase à une fin de phrase d'une ligne tirée par graine."""
    rng = random.Random(f"{graine}:insertion:{id_}")
    lignes = texte.split("\n")
    pleines = [i for i, x in enumerate(lignes) if x.strip()]
    i = rng.choice(pleines)
    fins = [d + len(p) for d, p in phrases(lignes[i], langue)] or [len(lignes[i])]
    k = rng.choice(fins)
    lignes[i] = f"{lignes[i][:k]} {phrase}{lignes[i][k:]}"
    return "\n".join(lignes)


def inserer_canaris(ch: Chemins, cfg: CorpusConfig, canaris: list[dict]) -> dict:
    """Écrit `brut+canaris/` : les canaris naturels dans des documents gardés par le
    nettoyage, une répétition par document. Écrit la liste (`ch.canaris`)."""
    entree = _paquets(ch.brut)
    sortie = Etape(ch.brut_canaris)
    if sortie.complet:
        return sortie.etat
    docs = ((d["id"], d["langue"]) for _, p in entree for d in lire_lignes(p)
            if _gardable(d, cfg.sources, cfg))  # fmt: skip
    cible = canaries.choisir(docs, canaris, "naturel", cfg.graine)
    canaries.ecrire(canaris, ch.canaris)
    for n, p in entree:
        if sortie.fini(n):
            continue
        lignes, inseres = [], 0
        for d in lire_lignes(p):
            if d["id"] in cible:
                c = canaris[cible[d["id"]]]
                d = d | {"texte": _inserer_naturel(d["texte"], d["langue"], c["phrase"],
                                                   cfg.graine, d["id"])}  # fmt: skip
                inseres += 1
            lignes.append(d)
        ecrire_table({k: [d[k] for d in lignes] for k in SCHEMA_BRUT.names}, SCHEMA_BRUT,
                     sortie.chemin_paquet(n))  # fmt: skip
        sortie.finir(n, {"documents": len(lignes), "canaris": inseres})
    sortie.completer()
    return sortie.etat


# --- passe A : nettoyer, fenêtres, détecter, propager dans le document -----------------


def _preparer(d: dict) -> tuple:
    cfg: CorpusConfig = _etat["cfg"]
    texte, raison = nettoyer(d["texte"], cfg.sources[d["source"]], cfg.nettoyage)
    if raison:
        return d, None, raison, None, None
    limite = cfg.jetons_fenetre - cfg.reserve_canari
    phr, fen = decouper_document(texte, d["langue"], _etat["compter"], limite)
    if not phr:
        return d, None, "sans phrase", None, None
    return d, texte, None, phr, fen


def _chaine_doc(d: dict, cfg: CorpusConfig, mode: str) -> tuple[str, str | None]:
    """(chaîne de détection du document, chaîne de contrôle sans GLiNER ou None)."""
    if mode == "tout" or tirage(cfg.graine, "gliner", d["id"]) < cfg.gliner.part:
        return d["langue"], (f"{d['langue']}_sans_gliner" if mode == "10pct" else None)
    return f"{d['langue']}_sans_gliner", None


def _propager_doc(args: tuple) -> tuple:
    textes, chemin, controle = args
    icfg: IngestConfig = _etat["icfg"]
    detectees = _zones_de(chemin, textes)
    comptes = prop.comptes_detectes(textes, detectees, icfg.detection.propagation_min)
    zones = propager(textes, detectees, icfg.detection.propagation_min)
    ratees: Counter = Counter()
    if controle:  # zones de la chaîne complète qu'aucune zone sans GLiNER ne recouvre
        for zs, zc in zip(detectees, _zones_de(controle, textes), strict=True):
            for z in zs:
                ratees[f"{z.type}_total"] += 1
                if not any(c.debut < z.fin and z.debut < c.fin for c in zc):
                    ratees[str(z.type)] += 1
    return zones, comptes, dict(ratees)


def _vus(chemin: Path, n: int) -> sqlite3.Connection:
    con = sqlite3.connect(chemin)
    con.execute("CREATE TABLE IF NOT EXISTS vu (sha TEXT PRIMARY KEY, paquet INTEGER)")
    con.execute("DELETE FROM vu WHERE paquet >= ?", (n,))  # reprise : paquet refait
    return con


def passe_a(ch: Chemins, cfg: CorpusConfig, icfg: IngestConfig,
            detection: dict[str, Detection], mode: str, lot_detection: int, arret=None
            ) -> Etape:  # fmt: skip
    entree = _paquets(ch.brut_canaris)
    sortie = Etape(ch.detecte)
    if sortie.complet:
        return sortie
    (ch.travail).mkdir(parents=True, exist_ok=True)
    with _carte(cfg, icfg) as carte:
        for n, p in entree:
            if sortie.fini(n):
                continue
            vus = _vus(ch.travail / "vus.sqlite", n)
            rejets: Counter = Counter()
            gardes, shas = [], set()
            for d, texte, raison, phr, fen in carte(_preparer, list(lire_lignes(p))):
                if raison is None:
                    sha = empreinte(texte)
                    if sha in shas or vus.execute("SELECT 1 FROM vu WHERE sha = ?",
                                                  (sha,)).fetchone():  # fmt: skip
                        raison = "doublon"
                    else:
                        shas.add(sha)
                if raison:
                    rejets[raison] += 1
                    continue
                gardes.append((d, texte, phr, fen))
            vus.executemany("INSERT INTO vu VALUES (?, ?)", ((s, n) for s in sorted(shas)))
            # Détection : par chaîne, phrases du paquet, cache du paquet.
            par_chaine: dict[str, list[str]] = {c: [] for c in _CHAINES}
            choix = []
            for d, texte, phr, _ in gardes:
                c, controle = _chaine_doc(d, cfg, mode)
                textes = [texte[a:b] for a, b in phr]
                par_chaine[c] += textes
                if controle:
                    par_chaine[controle] += textes
                choix.append((textes, c, controle))
            caches = {c: ch.travail / "cache" / c / f"paquet-{n:05d}.sqlite" for c in _CHAINES}
            for c, textes in par_chaine.items():
                if textes:
                    remplir_cache(textes, caches[c], detection[c], lot_detection)
            args = [(t, str(caches[c]), str(caches[k]) if k else None) for t, c, k in choix]
            comptes: dict[str, list[int]] = {}
            ratees: Counter = Counter()
            lignes = []
            for (d, texte, phr, fen), (zones, cpt, rat) in zip(
                gardes, carte(_propager_doc, args), strict=True
            ):
                for s, (k, r) in cpt.items():
                    x = comptes.setdefault(s, [len(TypeNom), 0, 0])
                    x[0], x[1], x[2] = min(x[0], r), x[1] + k, x[2] + 1
                ratees.update(rat)
                lignes.append({
                    "id": d["id"], "source": d["source"], "langue": d["langue"], "texte": texte,
                    "phrases": json.dumps(phr), "fenetres": json.dumps(fen),
                    "zones": json.dumps([[[z.debut, z.fin, str(z.type)] for z in zs]
                                         for zs in zones]),
                    "gliner": choix[len(lignes)][1] in ("fr", "en"),
                })  # fmt: skip
            cles = sorted(comptes)
            ecrire_table({"chaine": cles, "rang": [comptes[s][0] for s in cles],
                          "detectees": [comptes[s][1] for s in cles],
                          "documents": [comptes[s][2] for s in cles]},
                         SCHEMA_COMPTES, sortie.chemin_paquet(n, "comptes"))  # fmt: skip
            ecrire_table({k: [x[k] for x in lignes] for k in SCHEMA_DETECTE.names},
                         SCHEMA_DETECTE, sortie.chemin_paquet(n))  # fmt: skip
            vus.commit()
            vus.close()
            sortie.finir(n, {"entrees": len(gardes) + sum(rejets.values()), "gardes": len(gardes),
                             "rejets": dict(sorted(rejets.items())),
                             "ratees_sans_gliner": dict(sorted(ratees.items()))})  # fmt: skip
            if arret:
                arret("detecte", n)
    sortie.completer()
    return sortie


# --- barrières : comptes, candidates, liste globale, canaris forcés -------------------


def _barriere_candidates(ch: Chemins, cfg: CorpusConfig, canaris: list[dict] | None) -> None:
    etat = Etape(ch.travail / "candidates")
    if etat.complet:
        return
    chemin = ch.travail / "chaines.sqlite"
    chemin.unlink(missing_ok=True)
    con = prop.ouvrir_chaines(chemin)
    for n, _ in _paquets(ch.detecte):
        lignes = lire_lignes(Etape(ch.detecte).chemin_paquet(n, "comptes"))
        prop.ajouter_detectees(con, ((x["chaine"], x["rang"], x["detectees"], x["documents"])
                                     for x in lignes))  # fmt: skip
    con.commit()
    prop.sauver(prop.automate(prop.candidates(con, cfg.propagation.documents_min)),
                ch.travail / "candidates.pkl")  # fmt: skip
    con.close()
    if canaris is not None:
        docs = ((d["id"], d["langue"]) for _, p in _paquets(ch.detecte) for d in lire_lignes(p))
        canaries.choisir(docs, canaris, "force", cfg.graine)
        canaries.ecrire(canaris, ch.canaris)
    etat.completer()


def passe_b(ch: Chemins, cfg: CorpusConfig, arret=None) -> Etape:
    sortie = Etape(ch.occurrences)
    if sortie.complet:
        return sortie
    a = prop.charger(ch.travail / "candidates.pkl")
    for n, p in _paquets(ch.detecte):
        if sortie.fini(n):
            continue
        c: Counter = Counter()
        for d in lire_lignes(p):
            c.update(
                prop.compter_occurrences(a, (d["texte"][x:y] for x, y in json.loads(d["phrases"])))
            )
        cles = sorted(c)
        ecrire_table({"chaine": cles, "occurrences": [c[s] for s in cles]}, SCHEMA_OCCURRENCES,
                     sortie.chemin_paquet(n))  # fmt: skip
        sortie.finir(n, {"chaines": len(cles)})
        if arret:
            arret("occurrences", n)
    sortie.completer()
    return sortie


def _barriere_globales(ch: Chemins, cfg: CorpusConfig) -> dict:
    etat = Etape(ch.travail / "globales")
    if etat.complet:
        return etat.etat
    con = prop.ouvrir_chaines(ch.travail / "chaines.sqlite")
    con.execute("UPDATE chaine SET occurrences = 0")
    for _, p in _paquets(ch.occurrences):
        prop.ajouter_occurrences(con, ((x["chaine"], x["occurrences"]) for x in lire_lignes(p)))
    con.commit()
    globales = list(prop.globales(con, cfg.propagation.documents_min, cfg.propagation.part_min))
    (n_cand,) = con.execute("SELECT count(*) FROM chaine WHERE documents >= ?",
                            (cfg.propagation.documents_min,)).fetchone()  # fmt: skip
    con.close()
    prop.sauver(prop.automate(globales), ch.travail / "globales.pkl")
    etat.completer(candidates=n_cand, globales=len(globales))
    return etat.etat


# --- passe C : liste globale, remplacer, relations, [P], canaris forcés ---------------


def _fenetres_doc(args: tuple) -> list[dict]:
    d, zones, a_p = args
    icfg: IngestConfig = _etat["icfg"]
    texte, phr = d["texte"], json.loads(d["phrases"])
    out = []
    for i0, i1, jetons in json.loads(d["fenetres"]):
        textes = [texte[a:b] for a, b in phr[i0:i1]]
        seps = [""] + ["\n" if "\n" in texte[phr[i - 1][1] : phr[i][0]] else " "
                       for i in range(i0 + 1, i1)]  # fmt: skip
        f = marquer_fenetre(textes, seps, zones[i0:i1], d["langue"], a_p, icfg)
        out.append(f | {"jetons": jetons})
    return out


def _inserer_force(f: dict, phrase: str, jetons: int, a_p: bool, rng: random.Random) -> dict:
    """Le canari forcé, en clair, à une frontière de phrase de la fenêtre."""
    texte = f["texte"]
    k = rng.choice([0, *f["bornes"]])
    seg = f"[P] {phrase} [/P]" if a_p else phrase
    texte = f"{seg} {texte}" if k == 0 else f"{texte[:k]} {seg}{texte[k:]}"
    return f | {"texte": texte, "n_props": f["n_props"] + (1 if a_p else 0),
                "jetons": f["jetons"] + jetons}  # fmt: skip


def passe_c(ch: Chemins, cfg: CorpusConfig, icfg: IngestConfig, canaris: list[dict] | None,
            arret=None) -> Etape:  # fmt: skip
    sortie = Etape(ch.final)
    if sortie.complet:
        return sortie
    a = prop.charger(ch.travail / "globales.pkl")
    compter = compteur(cfg.decoupeur)
    forces: dict[str, int] = {}
    for k, c in enumerate(canaris or []):
        if c["genre"] == "force":
            forces.update(dict.fromkeys(c["documents"], k))
            if compter([c["phrase"]])[0] + 1 > cfg.reserve_canari:
                raise ValueError(f"canari {c['id']} plus long que la réserve")
    with _carte(cfg, icfg) as carte:
        for n, p in _paquets(ch.detecte):
            if sortie.fini(n):
                continue
            docs, args = [], []
            for d in lire_lignes(p):
                texte, phr = d["texte"], json.loads(d["phrases"])
                zones = [[Zone(x, y, TypeNom(t), frozenset()) for x, y, t in zs]
                         for zs in json.loads(d["zones"])]  # fmt: skip
                zones = [
                    prop.appliquer(a, texte[x:y], zs) for (x, y), zs in zip(phr, zones, strict=True)
                ]
                a_p = tirage(cfg.graine, "p", d["id"]) < cfg.part_p
                docs.append((d, a_p))
                args.append((d, zones, a_p))
            lignes = []
            for (d, a_p), fen in zip(docs, carte(_fenetres_doc, args), strict=True):
                if d["id"] in forces:
                    c = canaris[forces[d["id"]]]
                    rng = random.Random(f"{cfg.graine}:force:{d['id']}")
                    i = rng.randrange(len(fen))
                    fen[i] = _inserer_force(fen[i], c["phrase"], compter([c["phrase"]])[0] + 1,
                                            a_p, rng)  # fmt: skip
                for i, f in enumerate(fen):
                    lignes.append({"id": f"{d['id']}#{i}", "document": d["id"],
                                   "source": d["source"], "langue": d["langue"], "a_p": a_p,
                                   **f})  # fmt: skip
            ecrire_table({k: [x[k] for x in lignes] for k in SCHEMA_FINAL.names}, SCHEMA_FINAL,
                         sortie.chemin_paquet(n))  # fmt: skip
            sortie.finir(n, {"fenetres": len(lignes)})
            if arret:
                arret("final", n)
    sortie.completer()
    return sortie


def chaine(ch: Chemins, cfg: CorpusConfig, icfg: IngestConfig, detection: dict[str, Detection],
           mode: str, lot_detection: int, arret=None) -> dict:  # fmt: skip
    """Passe A, barrière, passe B, barrière, passe C. `arret(étape, paquet)` : appelé après
    chaque paquet fini (les tests y simulent une coupure)."""
    if mode not in ("tout", "10pct"):
        raise ValueError(f"mode GLiNER inconnu : {mode}")
    canaris = canaries.lire(ch.canaris) if ch.canaris.exists() else None
    passe_a(ch, cfg, icfg, detection, mode, lot_detection, arret)
    _barriere_candidates(ch, cfg, canaris)
    passe_b(ch, cfg, arret)
    globales = _barriere_globales(ch, cfg)
    passe_c(ch, cfg, icfg, canaris, arret)
    return {"mode": mode, "candidates": globales["candidates"], "globales": globales["globales"]}


# --- bilan --------------------------------------------------------------------------------


def bilan(ch: Chemins) -> dict:
    """Jetons par source et par langue, rejets, noms et nombres pour 1 000 jetons, canaris."""
    jetons: Counter = Counter()
    langues: Counter = Counter()
    noms = nombres = fenetres = 0
    canaris = canaries.lire(ch.canaris) if ch.canaris.exists() else []
    phrases_forces = {c["phrase"]: c["id"] for c in canaris if c["genre"] == "force"}
    trouves: Counter = Counter()
    documents = set()
    naturels = {i for c in canaris if c["genre"] == "naturel" for i in c["documents"]}
    for _, p in _paquets(ch.final):
        for x in lire_lignes(p):
            fenetres += 1
            jetons[x["source"]] += x["jetons"]
            langues[x["langue"]] += x["jetons"]
            ms = json.loads(x["marques"])
            noms += sum(1 for m in ms if m["genre"] == "NOM")
            nombres += sum(1 for m in ms if m["genre"] != "NOM")
            if x["document"] in naturels:
                documents.add(x["document"])
            for ph, i in phrases_forces.items():
                if ph in x["texte"]:
                    trouves[i] += 1
    rejets: Counter = Counter()
    ratees: Counter = Counter()
    det = Etape(ch.detecte)
    for n in det.paquets():
        rejets.update(det.bilan(n)["rejets"])
        ratees.update(det.bilan(n)["ratees_sans_gliner"])
    total = sum(jetons.values())
    attendus = {c["id"]: c["frequence"] for c in canaris if c["genre"] == "force"}
    return {
        "fenetres": fenetres, "jetons": total,
        "jetons_par_source": dict(sorted(jetons.items())),
        "parts_langues": {k: v / total for k, v in sorted(langues.items())} if total else {},
        "rejets": dict(sorted(rejets.items())),
        "ratees_sans_gliner": dict(sorted(ratees.items())),
        "noms_pour_1000": 1000 * noms / total if total else 0.0,
        "nombres_pour_1000": 1000 * nombres / total if total else 0.0,
        "canaris_forces_trouves": sum(trouves.values()),
        "canaris_forces_attendus": sum(attendus.values()),
        "canaris_forces_manquants": sorted(i for i, f in attendus.items() if trouves[i] < f),
        "documents_naturels_trouves": len(documents),
        "documents_naturels_attendus": len(naturels),
        "globales": Etape(ch.travail / "globales").etat.get("globales"),
    }  # fmt: skip


def detections(icfg: IngestConfig, dcfg) -> dict[str, Detection]:
    """Les quatre chaînes de détection, comme `ccm convertir` : fr à quatre détecteurs,
    en = `detecteurs_en` ; chacune sans GLiNER pour le mode `10pct`."""
    from ccm.ner.union import detecter

    gliner = icfg.detection.gliner.model_copy(update={"lot": dcfg.lot_gliner})
    det = icfg.detection.model_copy(update={"gliner": gliner})
    out = {}
    for lg, ds in (("fr", det.detecteurs), ("en", dcfg.detecteurs_en)):
        for nom, garder in ((lg, ds), (f"{lg}_sans_gliner", tuple(d for d in ds if d != "gliner"))):
            c = icfg.model_copy(update={"detection": det.model_copy(update={"detecteurs": garder})})
            out[nom] = lambda ts, c=c: detecter(ts, c)
    return out
