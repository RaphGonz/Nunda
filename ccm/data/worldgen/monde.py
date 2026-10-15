"""Générateur de monde d'un dossier synthétique (SPEC.md §12, « Corpus synthétique »).

Un monde = personnes avec un rôle, sociétés, lieux, événements datés. Cas durs :
alias (« dit »), deux personnes de même nom de famille, deux personnes de même nom
complet. Noms courants ou inventés ; aucun nom complet de la liste d'exclusion
(personnes de Wikidata). Deux réservoirs disjoints : `entrainement` et `test`.
"""

import hashlib
import random
import unicodedata
from datetime import date, time, timedelta
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from ccm.config import WorldgenConfig

Reservoir = Literal["entrainement", "test"]
RESERVOIRS_YAML = Path(__file__).with_name("reservoirs.yaml")
EXCLUS_WIKIDATA = Path(__file__).with_name("exclus_wikidata.txt")
VERIFIES_WIKIDATA = Path(__file__).with_name("verifies_wikidata.txt")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Personne(_Strict):
    id: int
    genre: Literal["M", "F"]
    prenom: str
    nom: str
    role: str
    surnom: str | None = None


class Societe(_Strict):
    id: int
    nom: str


class Lieu(_Strict):
    id: int
    genre: Literal["COMMUNE", "ADRESSE"]
    nom: str


class Evenement(_Strict):
    id: int
    type: str
    date: date
    heure: time
    lieu: int
    participants: tuple[int, ...]
    societes: tuple[int, ...]
    montants: tuple[Decimal, ...]


class CasDurs(_Strict):
    alias: bool
    meme_famille: bool
    meme_nom_complet: bool


class Monde(_Strict):
    graine: int
    reservoir: Reservoir
    cas: CasDurs
    personnes: tuple[Personne, ...]
    societes: tuple[Societe, ...]
    lieux: tuple[Lieu, ...]
    evenements: tuple[Evenement, ...]


def cle(chaine: str) -> str:
    """Clé de comparaison : NFKC, minuscules, sans accents, tirets et espaces réduits."""
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", chaine).casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.replace("-", " ").split())


def reservoir_de(chaine: str) -> Reservoir:
    """Partage stable des chaînes entre les deux réservoirs, par empreinte de la clé."""
    octet = hashlib.sha256(cle(chaine).encode()).digest()[0]
    return "entrainement" if octet % 2 == 0 else "test"


def charger_exclusion(chemin: Path) -> frozenset[str]:
    """Liste d'exclusion : un nom complet par ligne (UTF-8), rendue sous forme de clés."""
    with chemin.open(encoding="utf-8") as f:
        return frozenset(k for k in (cle(ligne) for ligne in f) if k)


@cache
def _reservoirs() -> dict[str, tuple[str, ...]]:
    with RESERVOIRS_YAML.open(encoding="utf-8") as f:
        return {k: tuple(v) for k, v in yaml.safe_load(f).items()}


class _Tireur:
    def __init__(self, rng: random.Random, cfg: WorldgenConfig, reservoir: Reservoir):
        self.rng = rng
        self.cfg = cfg
        self.reservoir = reservoir
        self.r = _reservoirs()
        self.pris: set[str] = set()

    def entre(self, intervalle: tuple[int, int]) -> int:
        return self.rng.randint(*intervalle)

    def unique(self, tirer, accepte=lambda s: True) -> str:
        """Tire jusqu'à une chaîne du bon réservoir, inédite dans le monde, acceptée."""
        for _ in range(self.cfg.essais_max):
            s = tirer()
            if reservoir_de(s) == self.reservoir and cle(s) not in self.pris and accepte(s):
                self.pris.add(cle(s))
                return s
        raise RuntimeError(f"aucun tirage accepté après {self.cfg.essais_max} essais")

    def invente(self, fins: str, n: tuple[int, int] = (1, 2)) -> str:
        mot = "".join(self.rng.choice(self.r["syllabes"]) for _ in range(self.entre(n)))
        fin = self.rng.choice(self.r[fins])
        if mot[-1] in "aeiouy" and fin[0] in "aeiouy":
            mot = mot[:-1]  # « Rilo » + « eau » → « Rileau »
        return mot[0].upper() + mot[1:] + fin

    def inventer_ou_choisir(self, fins: str, liste: str) -> str:
        if self.rng.random() < self.cfg.part_noms_inventes:
            return self.invente(fins)
        return self.rng.choice(self.r[liste])

    def prenom(self, genre: str, accepte) -> str:
        """Prénom du bon réservoir, accepté ; deux personnes peuvent le partager."""
        sexe = genre.lower()
        for _ in range(self.cfg.essais_max):
            s = self.inventer_ou_choisir(f"fins_prenom_{sexe}", f"prenoms_{sexe}")
            if reservoir_de(s) == self.reservoir and accepte(s):
                return s
        raise RuntimeError(f"aucun prénom accepté après {self.cfg.essais_max} essais")


def generer_monde(
    graine: int, reservoir: Reservoir, cfg: WorldgenConfig, exclus: frozenset[str]
) -> Monde:
    """Monde d'un dossier. Même graine, même réservoir, même config : même monde."""
    rng = random.Random(graine)
    t = _Tireur(rng, cfg, reservoir)

    def libre(prenom: str, nom: str) -> bool:
        return cle(f"{prenom} {nom}") not in exclus

    # Personnes : noms de famille deux à deux distincts avant les cas durs.
    personnes: list[dict] = []
    for i in range(t.entre(cfg.personnes)):
        genre = "F" if rng.random() < cfg.part_femmes else "M"
        nom = t.unique(lambda: t.inventer_ou_choisir("fins_nom", "noms"))
        prenom = t.prenom(genre, lambda p, nom=nom: libre(p, nom))
        personnes.append(
            dict(id=i, genre=genre, prenom=prenom, nom=nom, role=rng.choice(cfg.roles))
        )

    cas = CasDurs(
        alias=rng.random() < cfg.part_alias,
        meme_famille=rng.random() < cfg.part_meme_famille,
        meme_nom_complet=rng.random() < cfg.part_meme_nom_complet,
    )
    ordre = rng.sample(range(len(personnes)), 5)
    if cas.alias:
        personnes[ordre[0]]["surnom"] = t.unique(lambda: rng.choice(t.r["surnoms"]))
    if cas.meme_famille:
        a, b = personnes[ordre[1]], personnes[ordre[2]]
        b["nom"] = a["nom"]
        b["prenom"] = t.prenom(
            b["genre"], lambda p: cle(p) != cle(a["prenom"]) and libre(p, a["nom"])
        )
    if cas.meme_nom_complet:
        a, b = personnes[ordre[3]], personnes[ordre[4]]
        b.update(genre=a["genre"], prenom=a["prenom"], nom=a["nom"])

    societes = [
        Societe(id=i, nom=t.unique(lambda: _nom_societe(t))) for i in range(t.entre(cfg.societes))
    ]
    lieux = []
    for i in range(t.entre(cfg.lieux)):
        commune = t.unique(lambda: t.invente("fins_commune"))
        if rng.random() < cfg.part_adresses:
            rue = rng.choice(t.r["rues"])
            lieux.append(
                Lieu(id=i, genre="ADRESSE", nom=f"{t.entre(cfg.numero_rue)} {rue}, {commune}")
            )
        else:
            lieux.append(Lieu(id=i, genre="COMMUNE", nom=commune))

    evenements = _evenements(t, len(personnes), len(societes), len(lieux))
    return Monde(
        graine=graine,
        reservoir=reservoir,
        cas=cas,
        personnes=tuple(Personne(**p) for p in personnes),
        societes=tuple(societes),
        lieux=tuple(lieux),
        evenements=evenements,
    )


def _nom_societe(t: _Tireur) -> str:
    racine = t.inventer_ou_choisir("fins_nom", "noms")
    nom = f"{t.rng.choice(t.r['formes_societe'])} {racine}"
    if t.rng.random() < t.cfg.part_activite:
        nom += f" {t.rng.choice(t.r['activites'])}"
    return nom


def _evenements(t: _Tireur, n_per: int, n_soc: int, n_lieux: int) -> tuple[Evenement, ...]:
    cfg, rng = t.cfg, t.rng
    etendue = (cfg.fin - cfg.debut).days - cfg.duree_dossier_jours
    debut = cfg.debut + timedelta(days=rng.randint(0, etendue))
    bruts = []
    for _ in range(t.entre(cfg.evenements)):
        type_ = rng.choice(cfg.types_evenement)
        n_part = min(t.entre(cfg.participants), n_per)
        montants = ()
        if type_ in cfg.types_avec_montant:
            montants = tuple(
                Decimal(t.entre(cfg.montant_centimes)) / 100 for _ in range(t.entre(cfg.montants))
            )
        bruts.append(
            dict(
                type=type_,
                date=debut + timedelta(days=rng.randint(0, cfg.duree_dossier_jours)),
                heure=time(rng.randint(0, 23), rng.randint(0, 59)),
                lieu=rng.randrange(n_lieux),
                participants=tuple(sorted(rng.sample(range(n_per), n_part))),
                societes=(rng.randrange(n_soc),) if type_ in cfg.types_avec_societe else (),
                montants=montants,
            )
        )
    bruts.sort(key=lambda e: (e["date"], e["heure"]))
    return tuple(Evenement(id=i, **e) for i, e in enumerate(bruts))


def mondes_corpus(cfg: WorldgenConfig, exclus: frozenset[str]):
    """(partie, monde) de chaque dossier du corpus, graines consécutives par partie."""
    for nom, partie in cfg.corpus.items():
        for i in range(partie.dossiers):
            yield nom, generer_monde(partie.graine + i, partie.reservoir, cfg, exclus)
