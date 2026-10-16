"""Pièces d'un dossier synthétique, rédigées par gabarits (SPEC.md §12).

Une pièce est une suite de lignes (titre, champ, phrase, ligne de tableau). Chaque ligne
déclare ses faits : position et surface de chaque nom, nombre, date et heure, avec
l'entité ou la valeur du monde. Une ligne d'événement porte l'identifiant de
l'événement et sa version (0 : celle du monde ; 1 : la version contradictoire du
second témoin). Le contrôle de provenance (`controle.py`) relit ces déclarations.
"""

import random
import re
from datetime import date, time, timedelta
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Literal

import yaml

from ccm.config import WorldgenConfig
from ccm.data.worldgen.monde import Evenement, Monde, Personne, Societe, _reservoirs, _Strict

GABARITS_YAML = Path(__file__).with_name("gabarits.yaml")
MOIS = (
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre"
).split()
# Texte fixe écrit par le code autour des faits (titres, articles, prépositions).
TEXTE_CODE = "M. Mme Me la l' société à au , dit et qu' d'"

Genre = Literal["PER", "ORG", "LIEU", "REF", "NUM", "DATE", "HEURE"]


class Fait(_Strict):
    debut: int
    fin: int
    surface: str
    genre: Genre
    entite: int | None = None  # personne, société ou lieu
    forme: str | None = None  # forme du nom (COMPLET, NOM_PRENOM, ...)
    valeur: str | None = None  # décimal, date ISO, heure HH:MM, référence
    unite: str | None = None


class Ligne(_Strict):
    texte: str
    genre: Literal["EN_TETE", "CHAMP", "PHRASE", "LIGNE_TABLEAU"]
    gabarit: str
    evenement: int | None = None
    version: int = 0
    faits: tuple[Fait, ...]


class Piece(_Strict):
    id: str
    type: str
    date: date
    reference: str
    auteur: int | None = None  # enquêteur
    locuteur: int | None = None  # personne entendue
    signataire: int | None = None
    expediteur: int | None = None  # société expéditrice ou titulaire du compte
    periode: tuple[date, ...] = ()
    evenements: tuple[int, ...]
    lignes: tuple[Ligne, ...]


class Conflit(_Strict):
    evenement: int
    champ: Literal["HEURE", "MONTANT", "PERSONNE"]
    pieces: tuple[str, str]  # (version du monde, version contradictoire)


class Dossier(_Strict):
    id: str
    monde: Monde
    variante: Evenement | None = None  # seconde version de l'événement en conflit
    conflit: Conflit | None = None
    pieces: tuple[Piece, ...]

    def evenement(self, id_: int, version: int) -> Evenement:
        if version == 1:
            assert self.variante is not None and self.variante.id == id_
            return self.variante
        return self.monde.evenements[id_]


@cache
def gabarits(reservoir: str) -> dict:
    with GABARITS_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)[reservoir]


# --- Formes des noms et des valeurs --------------------------------------------------


def initiales(p: Personne) -> str:
    lettres = [m[0] for m in re.split(r"[-\s]+", p.prenom) if m]
    lettres += [m[0] for m in p.nom.split() if m[0].isupper()]
    return "".join(f"{c.upper()}." for c in lettres)


def forme_personne(p: Personne, forme: str) -> str:
    match forme:
        case "COMPLET":
            return f"{p.prenom} {p.nom}"
        case "NOM_PRENOM":
            return f"{p.nom.upper()} {p.prenom}"
        case "INITIALES":
            return initiales(p)
        case "NOM_SEUL" | "TITRE_NOM":
            return p.nom
        case "SURNOM":
            assert p.surnom
            return p.surnom
    raise ValueError(forme)


def racine_societe(s: Societe) -> str:
    """Nom sans forme juridique ni activité : « SARL Bormac Transports » → « Bormac »."""
    mots = s.nom.split()[1:]
    if len(mots) > 1 and mots[-1] in _reservoirs()["activites"]:
        mots = mots[:-1]
    return " ".join(mots)


def forme_societe(s: Societe, forme: str) -> str:
    return s.nom if forme == "COMPLET" else racine_societe(s)


def ecrire_montant(v: Decimal, rng: random.Random) -> str:
    q = v.quantize(Decimal("0.01"))
    entier, centimes = int(q), int((q - int(q)) * 100)
    chiffres = str(entier)
    if rng.random() < 0.7:  # séparateur de milliers
        groupes = []
        while chiffres:
            groupes.insert(0, chiffres[-3:])
            chiffres = chiffres[:-3]
        chiffres = " ".join(groupes)
    s = chiffres if centimes == 0 and rng.random() < 0.5 else f"{chiffres},{centimes:02d}"
    return f"{s} {rng.choice(['€', 'euros'])}"


def ecrire_date(d: date, rng: random.Random) -> str:
    if rng.random() < 0.3:
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{jour} {MOIS[d.month - 1]} {d.year}"


def ecrire_heure(h: time, rng: random.Random) -> str:
    style = rng.randrange(3)
    if style == 0:
        return f"{h.hour} h {h.minute:02d}" if h.minute else f"{h.hour} h"
    if style == 1:
        return f"{h.hour}h{h.minute:02d}"
    return f"{h.hour:02d}:{h.minute:02d}"


# --- Rédaction d'une ligne -----------------------------------------------------------

_CHAMP = re.compile(r"\{(\w+)\}")
_LIBELLE_CHAMP = re.compile(r"^[^:]{2,40} : ")
_VOYELLES = "aeiouyàâéèêîôûAEIOUYÀÂÉÈÊÎÔÛ"
# « que un » → « qu'un », « de Elodie » → « d'Elodie ».
_ELISION = re.compile(rf"\b([QqDd]u?)e (?=[{_VOYELLES}])")


class _Plume:
    """Rédige les lignes d'une pièce ; suit les noms déjà cités dans la pièce."""

    def __init__(self, rng: random.Random, dossier_monde: Monde, cfg: WorldgenConfig, g: dict):
        self.rng, self.m, self.r, self.g = rng, dossier_monde, cfg.redaction, g
        self.vus: set[int] = set()
        self.soc_vues: set[int] = set()
        self.piece: dict = {}

    # Morceau : (texte, fait sans position ou None). « , » final d'un DIT : fait "VIRGULE".
    def _personne(self, pid: int, formes: tuple[str, ...] | None = None) -> list:
        p = self.m.personnes[pid]
        if formes is None:
            formes = self.r.formes_suite if pid in self.vus else self.r.formes_premiere
        formes = tuple(f for f in formes if p.surnom or f not in ("DIT", "SURNOM"))
        forme = self.rng.choice(formes)
        self.vus.add(pid)

        def fait(f):
            return (forme_personne(p, f), dict(genre="PER", entite=pid, forme=f))

        if forme == "DIT":
            return [fait("COMPLET"), (", dit ", None), fait("SURNOM"), (",", "VIRGULE")]
        if forme == "TITRE_NOM":
            titre = "Me" if p.role == "AVOCAT" else ("Mme" if p.genre == "F" else "M.")
            return [(f"{titre} ", None), fait("TITRE_NOM")]
        return [fait(forme)]

    def _liste(self, parties: list[list]) -> list:
        out: list = []
        for i, morceaux in enumerate(parties):
            if i:
                out.append((" et " if i == len(parties) - 1 else ", ", None))
            out += morceaux
        return out

    def _societe(self, sid: int) -> list:
        s = self.m.societes[sid]
        forme = self.rng.choice(self.r.formes_societe) if sid in self.soc_vues else "COMPLET"
        self.soc_vues.add(sid)
        if forme == "COMPLET":
            article = "l'" if s.nom[0] in "AEIOU" else "la "
        else:
            article = "la société "
        fait = dict(genre="ORG", entite=sid, forme=forme)
        return [(article, None), (forme_societe(s, forme), fait)]

    def _lieu(self, lid: int) -> list:
        lieu = self.m.lieux[lid]
        prep = "au " if lieu.genre == "ADRESSE" else "à "
        return [(prep, None), (lieu.nom, dict(genre="LIEU", entite=lid))]

    def _montant(self, v: Decimal) -> list:
        fait = dict(genre="NUM", valeur=str(v.quantize(Decimal("0.01"))), unite="€")
        return [(ecrire_montant(v, self.rng), fait)]

    def _date(self, d: date) -> list:
        return [(ecrire_date(d, self.rng), dict(genre="DATE", valeur=d.isoformat()))]

    def _champ(self, nom: str, ev: Evenement | None) -> list:
        pc = self.piece
        match nom:
            case "P":
                return self._liste([self._personne(i) for i in ev.participants])
            case "A":
                return self._personne(ev.participants[0])
            case "B":
                return self._liste([self._personne(i) for i in ev.participants[1:]])
            case "a":
                return [("a" if len(ev.participants) == 1 else "ont", None)]
            case "S":
                return self._societe(ev.societes[0])
            case "M":
                return self._liste([self._montant(v) for v in ev.montants])
            case _ if nom.startswith("M") and nom[1:].isdigit():
                return self._montant(ev.montants[int(nom[1:])])
            case "D":
                return self._date(ev.date)
            case "H":
                h = ev.heure
                return [(ecrire_heure(h, self.rng), dict(genre="HEURE", valeur=f"{h:%H:%M}"))]
            case "L":
                return self._lieu(ev.lieu)
            case "DP":
                return self._date(pc["date"])
            case "D1" | "D2":
                return self._date(pc["periode"][int(nom[1]) - 1])
            case "REF":
                return [(pc["reference"], dict(genre="REF", valeur=pc["reference"]))]
            case "AUT":
                grade = self.rng.choice(self.g["grades"])
                formes = ("COMPLET", "NOM_PRENOM", "NOM_SEUL")
                return [(f"{grade} ", None)] + self._personne(pc["auteur"], formes)
            case "LOC":
                return self._personne(pc["locuteur"], self.r.formes_premiere)
            case "SUR":
                return self._personne(pc["locuteur"], ("SURNOM",))
            case "SIG":
                return self._personne(pc["signataire"], ("COMPLET", "NOM_PRENOM"))
            case "EXP":
                return self._societe(pc["expediteur"])[1:]  # sans article
        raise KeyError(nom)

    def ligne(self, modele: str, gabarit: str, genre=None, ev=None, version=0) -> Ligne:
        morceaux: list = []
        for i, bout in enumerate(_CHAMP.split(modele)):
            morceaux += self._champ(bout, ev) if i % 2 else [(bout, None)]
        texte, faits = "", []
        for i, (s, fait) in enumerate(morceaux):
            if fait == "VIRGULE":  # « X, dit S, a viré » mais « … dit S. »
                suite = "".join(t for t, _ in morceaux[i + 1 :])
                if not suite or not suite[0].isalpha() and suite[0] != " ":
                    continue
            elif not texte and s[:1].islower():
                s = s[0].upper() + s[1:]
            if fait is None:
                s = _ELISION.sub(r"\1'", s)
            if s[:1] in _VOYELLES and (m := re.search(r"\b([QqDd]u?)e $", texte)):
                texte = texte[: m.start()] + m[1] + "'"
            if fait not in (None, "VIRGULE"):
                faits.append(Fait(debut=len(texte), fin=len(texte) + len(s), surface=s, **fait))
            texte += s
        if genre is None:
            genre = "CHAMP" if _LIBELLE_CHAMP.match(texte) else "PHRASE"
        return Ligne(
            texte=texte,
            genre=genre,
            gabarit=gabarit,
            evenement=None if ev is None else ev.id,
            version=version,
            faits=tuple(faits),
        )


# --- Composition du dossier ----------------------------------------------------------


def _choisir(rng: random.Random, g: dict, chemin: str) -> tuple[str, str]:
    """Gabarit tiré au hasard dans g[a][b]... ; rend (texte, identifiant)."""
    liste = g
    for k in chemin.split("/"):
        liste = liste[k]
    i = rng.randrange(len(liste))
    return liste[i], f"{chemin}/{i}"


def noyaux_possibles(g: dict, ev: Evenement) -> list[int]:
    def possible(n: str) -> bool:
        return ("{B}" not in n or len(ev.participants) > 1) and (
            "{S}" not in n or bool(ev.societes)
        )

    return [i for i, n in enumerate(g["noyaux"][ev.type]) if possible(n)]


def _variante(rng: random.Random, m: Monde, cfg: WorldgenConfig, ev: Evenement, champ, exclus):
    if champ == "HEURE":
        minutes = ev.heure.hour * 60 + ev.heure.minute
        d = rng.randint(*cfg.redaction.decalage_heure_minutes) * rng.choice((-1, 1))
        m2 = (minutes + d) % (24 * 60)
        return ev.model_copy(update=dict(heure=time(m2 // 60, m2 % 60)))
    if champ == "MONTANT":
        k = rng.randrange(len(ev.montants))
        while True:
            v = Decimal(rng.randint(*cfg.montant_centimes)) / 100
            if v not in ev.montants:
                break
        montants = ev.montants[:k] + (v,) + ev.montants[k + 1 :]
        return ev.model_copy(update=dict(montants=montants))
    autres = [p.id for p in m.personnes if p.id not in ev.participants and p.id not in exclus]
    k = rng.randrange(len(ev.participants))
    parts = list(ev.participants)
    parts[k] = rng.choice(autres)
    return ev.model_copy(update=dict(participants=tuple(parts)))


def rediger_dossier(m: Monde, cfg: WorldgenConfig) -> Dossier:
    """Pièces d'un dossier. Même monde, même config : mêmes pièces."""
    r = cfg.redaction
    rng = random.Random(f"pieces-{m.graine}")
    g = gabarits(m.reservoir)
    evs = m.evenements
    par_type = {t: [e.id for e in evs if e.type in ts] for t, ts in r.types_par_piece.items()}

    # Types des pièces : un RAPPORT d'abord ; un CONTRAT par SIGNATURE au plus.
    n = rng.randint(*r.pieces)
    types = ["RAPPORT"] + rng.choices(list(r.poids_pieces), list(r.poids_pieces.values()), k=n - 1)
    signatures = list(par_type["CONTRAT"])
    rng.shuffle(signatures)
    contrats = iter(signatures)
    infos: list[dict] = []
    for t in types:
        info = dict(type=t, evenements=[])
        if t == "CONTRAT":
            e = next(contrats, None)
            if e is None:
                info["type"] = "RAPPORT"
            else:
                info["evenements"] = [e]
        elif not par_type[t]:
            info["type"] = "RAPPORT"
        infos.append(info)

    conflit = rng.random() < r.part_contradiction
    auditions = [i for i in infos if i["type"] == "PV_AUDITION"]
    if conflit and len(auditions) < 2:
        for info in infos[1:]:
            if len(auditions) == 2:
                break
            if info["type"] not in ("PV_AUDITION", "CONTRAT"):
                info["type"] = "PV_AUDITION"
                auditions.append(info)

    # Personnes et sociétés de chaque pièce.
    ids = [p.id for p in m.personnes]
    enqueteurs = [p.id for p in m.personnes if p.role == "ENQUETEUR"]
    locuteurs = rng.sample(ids, min(len(ids), len(auditions)))
    for k, info in enumerate(auditions):
        info["locuteur"] = locuteurs[k] if k < len(locuteurs) else rng.choice(ids)
    for info in infos:
        t = info["type"]
        if t in ("PV_AUDITION", "PV_CONSTATATION", "RAPPORT") and enqueteurs:
            info["auteur"] = rng.choice(enqueteurs)
        if t in ("COURRIER", "RELEVE"):
            info["expediteur"] = rng.randrange(len(m.societes))
        if t == "COURRIER":
            gerants = [p.id for p in m.personnes if p.role == "GERANT"] or ids
            info["signataire"] = rng.choice(gerants)

    def compatible(info: dict, e: Evenement) -> bool:
        return e.id in par_type[info["type"]] and (
            info["type"] != "PV_AUDITION" or info["locuteur"] not in e.participants
        )

    # Chaque événement va dans une pièce au moins ; une pièce vide en reçoit quelques-uns.
    libres = [i for i in infos if i["type"] != "CONTRAT"]
    for e in evs:
        rng.choice([i for i in libres if compatible(i, e)])["evenements"].append(e.id)
    for info in libres:
        if not info["evenements"]:
            cands = [e.id for e in evs if compatible(info, e)]
            k = min(len(cands), rng.randint(*r.evenements_piece))
            info["evenements"] = rng.sample(cands, k)

    # Version contradictoire : un événement, deux témoins, un champ différent.
    variante = conflit_ = None
    if conflit:
        a1, a2 = auditions[:2]
        loc = {a1["locuteur"], a2["locuteur"]}
        cands = [e for e in evs if compatible(a1, e) and compatible(a2, e)]
        if cands:
            e = rng.choice(cands)
            champs = [c for c in r.champs_contradiction if c != "MONTANT" or e.montants]
            champ = rng.choice(champs)
            variante = _variante(rng, m, cfg, e, champ, loc)
            for a in (a1, a2):
                if e.id not in a["evenements"]:
                    a["evenements"].append(e.id)
            a2["variante"] = e.id
            conflit_ = (e.id, champ, a1, a2)

    # Dates et références ; pièces rangées par date.
    for info in infos:
        info["evenements"] = sorted(set(info["evenements"]))
        dates = [evs[i].date for i in info["evenements"]]
        info["date"] = max(dates) + timedelta(days=rng.randint(*r.delai_piece_jours))
        info["reference"] = f"{info['date'].year}/{rng.randint(1, 99999):05d}"
        if info["type"] == "RELEVE":
            info["periode"] = (min(dates), max(dates))
    ordre = sorted(range(len(infos)), key=lambda i: (infos[i]["date"], i))
    pieces = []
    for rang, i in enumerate(ordre):
        infos[i]["id"] = f"P{rang + 1:02d}"
        pieces.append(_rediger_piece(rng, m, cfg, g, infos[i], variante))

    conflit_obj = None
    if conflit_:
        e_id, champ, a1, a2 = conflit_
        conflit_obj = Conflit(evenement=e_id, champ=champ, pieces=(a1["id"], a2["id"]))
    return Dossier(
        id=f"syn-{m.graine:07d}",
        monde=m,
        variante=variante,
        conflit=conflit_obj,
        pieces=tuple(pieces),
    )


def _rediger_piece(rng, m: Monde, cfg, g, info: dict, variante) -> Piece:
    plume = _Plume(rng, m, cfg, g)
    plume.piece = info
    t = info["type"]
    gp = f"pieces/{t}"
    lignes: list[Ligne] = []

    def fixe(cle: str, genre=None):
        modele, gid = _choisir(rng, g, f"{gp}/{cle}")
        lignes.append(plume.ligne(modele, gid, genre))

    def ev_de(e_id: int) -> tuple[Evenement, int]:
        if info.get("variante") == e_id:
            return variante, 1
        return m.evenements[e_id], 0

    def corps():
        for e_id in info["evenements"]:
            ev, version = ev_de(e_id)
            cadre, cid = _choisir(rng, g, f"cadres/{t}")
            k = rng.choice(noyaux_possibles(g, ev))
            noyau = g["noyaux"][ev.type][k]
            gid = f"{cid}+noyaux/{ev.type}/{k}"
            lignes.append(plume.ligne(cadre.replace("{N}", noyau), gid, None, ev, version))

    def evenementiel(cle: str):
        ev, version = ev_de(info["evenements"][0])
        modele, gid = _choisir(rng, g, f"{gp}/{cle}")
        lignes.append(plume.ligne(modele, gid, None, ev, version))

    fixe("titre", "EN_TETE")
    fixe("ref")
    if t in ("PV_AUDITION", "PV_CONSTATATION", "RAPPORT"):
        fixe("date")
        fixe("intro_auteur" if "auteur" in info else "intro")
        if t == "PV_AUDITION":
            fixe("identite")
            if m.personnes[info["locuteur"]].surnom:
                fixe("alias")
        corps()
        fixe("fin")
    elif t == "COURRIER":
        for cle in ("date", "objet", "intro"):
            fixe(cle)
        corps()
        fixe("fin")
        fixe("signature")
    elif t == "CONTRAT":
        for cle in ("parties", "prix", "fait", "signatures"):
            evenementiel(cle)
    elif t == "RELEVE":
        fixe("titulaire")
        fixe("periode")
        fixe("colonnes", "LIGNE_TABLEAU")
        for e_id in info["evenements"]:
            ev, version = ev_de(e_id)
            for k in range(len(ev.montants)):
                lib, gid = _choisir(rng, g, f"{gp}/libelles")
                modele = f"{{D}} | {lib} | {{M{k}}}"
                lignes.append(plume.ligne(modele, gid, "LIGNE_TABLEAU", ev, version))
    champs = ("auteur", "locuteur", "signataire", "expediteur", "periode")
    return Piece(
        id=info["id"],
        type=t,
        date=info["date"],
        reference=info["reference"],
        evenements=tuple(info["evenements"]),
        lignes=tuple(lignes),
        **{c: info[c] for c in champs if c in info},
    )
