"""Canaris de la mesure d'amnésie (SPEC.md §14).

600 faux faits sur des noms inventés : 300 naturels, insérés dans le corpus brut avant
l'anonymisation (ils mesurent la chaîne telle qu'elle est), et 300 forcés, insérés après,
noms en clair (ils mesurent ce que coûte un nom non détecté). Chaque genre : 100 canaris
répétés 1 fois, 100 répétés 10 fois, 100 répétés 100 fois ; 70 % en français, 30 % en anglais,
comme le corpus. Chaque répétition va dans un document différent de la même langue.

Un canari est une phrase à gabarit qui finit par un nom commun en minuscules, tiré d'une
liste fermée de 1 000 fins par langue (lexique Hunspell) : ni nom, ni nombre, ni date, la fin
n'est jamais masquée, et la mesure « rang de la vraie fin parmi 1 000 » a un sens. Les noms :
prénom courant des réservoirs de `worldgen` et nom de famille inventé, sans aucun nom
complet de la liste Wikidata (règle du §12).

La liste (`racine/canaris/canaris.json`) reste hors du corpus. Les canaris forcés mettent des
noms en clair dans des fichiers d'entraînement : c'est voulu par le §14, et ces noms sont
inventés (écart à la règle du §15, noté au journal).
"""

import heapq
import json
import random
from collections.abc import Iterable
from pathlib import Path

from ccm.config import CanarisConfig
from ccm.data.pretrain.etat import ecrire_atomique, tirage
from ccm.data.worldgen.monde import _reservoirs, cle

GENRES = ("naturel", "force")


def fins_candidates(dic: Path, langue: str, cfg: CanarisConfig, graine: int) -> list[str]:
    """`cfg.fins` noms communs en minuscules du dictionnaire Hunspell `dic` (.dic), tirés
    par graine. Français : drapeaux « S. » ou « X. » (pluriel en s ou x) ; anglais : « M » et
    « S » seuls (possessif et pluriel, sans drapeau de verbe)."""
    lo, hi = cfg.longueur_fin
    mots = set()
    for ligne in dic.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        mot, _, drapeaux = ligne.strip().partition("/")
        drapeaux = drapeaux.split()[0] if drapeaux.split() else ""
        if not (mot.isalpha() and mot.islower() and lo <= len(mot) <= hi):
            continue
        if langue == "fr" and drapeaux in ("S.", "X."):
            mots.add(mot)
        elif langue == "en" and drapeaux and set(drapeaux) <= {"M", "S"} and "M" in drapeaux:
            mots.add(mot)
    if len(mots) < cfg.fins:
        raise ValueError(f"{len(mots)} fins candidates en {langue}, {cfg.fins} demandées")
    return sorted(random.Random(f"{graine}:fins:{langue}").sample(sorted(mots), cfg.fins))


def _nom_invente(rng: random.Random) -> str:
    r = _reservoirs()
    prenom = rng.choice(r[rng.choice(("prenoms_m", "prenoms_f"))])
    mot = "".join(rng.choice(r["syllabes"]) for _ in range(rng.randint(2, 3)))
    fin = rng.choice(r["fins_nom"])
    if mot[-1] in "aeiouy" and fin[0] in "aeiouy":
        mot = mot[:-1]
    return f"{prenom} {mot[0].upper()}{mot[1:]}{fin}"


def generer(cfg: CanarisConfig, fins: dict[str, list[str]], exclus: frozenset[str], graine: int
            ) -> list[dict]:  # fmt: skip
    """Les canaris, sans documents. Même graine, même liste."""
    rng = random.Random(f"{graine}:canaris")
    noms_courants = {cle(n) for n in _reservoirs()["noms"]}
    pris: set[str] = set()
    out = []
    n_fr = round(cfg.part_fr * cfg.par_frequence)
    for genre in GENRES:
        for f in cfg.frequences:
            for k in range(cfg.par_frequence):
                langue = "fr" if k < n_fr else "en"
                while True:
                    nom = _nom_invente(rng)
                    famille = cle(nom.split(" ", 1)[1])
                    if cle(nom) not in exclus and cle(nom) not in pris and (
                            famille not in noms_courants):  # fmt: skip
                        pris.add(cle(nom))
                        break
                fin = rng.choice(fins[langue])
                gabarit = rng.choice(cfg.gabarits[langue])
                phrase = gabarit.format(nom=nom, fin=fin)
                out.append({
                    "id": f"{genre}-{len(out):03d}", "genre": genre, "langue": langue,
                    "frequence": f, "nom": nom, "phrase": phrase,
                    "prefixe": phrase[: phrase.rindex(fin)], "fin": fin, "fins": fins[langue],
                    "documents": [],
                })  # fmt: skip
    return out


def choisir(docs: Iterable[tuple[str, str]], canaris: list[dict], genre: str, graine: int
            ) -> dict[str, int]:  # fmt: skip
    """Documents (id, langue) qui reçoivent les répétitions des canaris de `genre` : chaque
    document au plus une répétition, tirés par graine sur l'id (les plus petits tirages).
    Remplit `documents` de chaque canari ; rend id → rang du canari dans `canaris`."""
    besoin: dict[str, int] = {}
    for c in canaris:
        if c["genre"] == genre:
            besoin[c["langue"]] = besoin.get(c["langue"], 0) + c["frequence"]
    tas: dict[str, list] = {lg: [] for lg in besoin}
    for id_, langue in docs:
        if langue not in tas:
            continue
        x = (-tirage(graine, f"canari-{genre}", id_), id_)
        if len(tas[langue]) < besoin[langue]:
            heapq.heappush(tas[langue], x)
        elif x > tas[langue][0]:
            heapq.heapreplace(tas[langue], x)
    ordre = {lg: [i for _, i in sorted(t, reverse=True)] for lg, t in tas.items()}
    for lg, ids in ordre.items():
        if len(ids) < besoin[lg]:
            raise ValueError(f"{len(ids)} documents en {lg} pour {besoin[lg]} canaris {genre}")
    out: dict[str, int] = {}
    pos = dict.fromkeys(ordre, 0)
    for k, c in enumerate(canaris):
        if c["genre"] != genre:
            continue
        lg = c["langue"]
        c["documents"] = ordre[lg][pos[lg] : pos[lg] + c["frequence"]]
        pos[lg] += c["frequence"]
        out.update(dict.fromkeys(c["documents"], k))
    return out


def ecrire(canaris: list[dict], chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    ecrire_atomique(chemin, json.dumps(canaris, ensure_ascii=False, indent=1).encode("utf-8"))


def lire(chemin: Path) -> list[dict]:
    return json.loads(chemin.read_text(encoding="utf-8"))
