"""Questions et vérité terrain du corpus synthétique (SPEC.md §12, §10 bis).

Environ 40 questions par dossier, de sept types. Chaque question porte : le message de
l'utilisateur (et l'historique d'un dialogue) avec ses faits déclarés ; les étapes de
justification, dans l'ordre du raisonnement (chaque étape : lignes équivalentes, la
première sert à la synthèse) ; la vérité propre au type (identités, calcul, déclaration,
personnes possibles, abstention) ; la synthèse de référence, écrite depuis le graphe de
faits. Les suites d'actions de référence (§10) s'écriront en phase 3 depuis ces données.

Références : « P03:4 » pour une ligne (pièce, rang de la ligne), « P03:4:1 » pour un fait
(ligne, rang du fait). Un nom de la question et le nom d'une ligne citée ont la même clé
(`cle`), sauf pour les questions d'identité et de dialogue qui demandent le contraire :
la règle d'ancrage (§11) relie alors chaque citation à la question sans note.
"""

import random
import re
from collections import defaultdict
from decimal import Decimal
from functools import cache
from operator import add, sub
from pathlib import Path
from typing import Literal

import yaml

from ccm.config import WorldgenConfig
from ccm.data.worldgen.monde import Evenement, _reservoirs, _Strict, cle
from ccm.data.worldgen.pieces import (
    _ELISION,
    _VOYELLES,
    MOIS,
    Dossier,
    Fait,
    assembler,
    ecrire_date,
    forme_personne,
    forme_societe,
)

QUESTIONS_YAML = Path(__file__).with_name("questions.yaml")
TYPES = (
    "FAIT_SIMPLE",
    "PLUSIEURS_ETAPES",
    "IDENTITE",
    "FAIT_ABSENT",
    "CONFLIT",
    "CALCUL",
    "DIALOGUE",
)
ATTRIBUTS = ("DATE", "HEURE", "LIEU", "MONTANT", "SOCIETE", "PERSONNE")
GENRE_ATTRIBUT = {
    "DATE": "DATE",
    "HEURE": "HEURE",
    "LIEU": "LIEU",
    "MONTANT": "NUM",
    "SOCIETE": "ORG",
    "PERSONNE": "PER",
}
FORMES_PER = ("COMPLET", "NOM_PRENOM", "INITIALES", "NOM_SEUL", "SURNOM")
POINTEUR = {"PER": "M", "ORG": "M", "LIEU": "M", "NUM": "N", "DATE": "N", "HEURE": "N"}

# Mots refusés dans une synthèse (règles du masque, §10 bis ; liste V à venir en phase 5).
NEGATIONS = frozenset("ne n' pas aucun aucune jamais non ni nullement sans".split())
NOMBRES = frozenset(
    (
        "zéro un une deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze "
        "quinze seize vingt vingts trente quarante cinquante soixante septante huitante "
        "nonante cent cents mille million millions milliard milliards demi demie double "
        "moitié triple dizaine dizaines centaine centaines premier première premiers "
        "premières second seconde seconds secondes"
    ).split()
)
JOURS = frozenset("lundi mardi mercredi jeudi vendredi samedi dimanche".split())


class Tour(_Strict):
    role: Literal["UTILISATEUR", "MODELE"]
    texte: str = ""
    faits: tuple[Fait, ...] = ()
    lignes: tuple[str, ...] = ()  # lignes citées par la réponse du modèle


class Etape(_Strict):
    role: Literal["CITE", "PREUVE", "CONFLIT"]
    lignes: tuple[str, ...]  # équivalentes ; la première sert à la synthèse


class Identite(_Strict):
    question: int  # rang du fait dans le message
    fait: str  # fait de la ligne citée qui désigne la même personne
    preuve: str | None  # ligne qui écrit les deux noms (« X, dit S »), sinon ressemblance


class Calcul(_Strict):
    operation: Literal["SOMME", "ECART", "DUREE", "MIN", "MAX"]
    postfixe: tuple[str, ...]  # faits et opérateurs du lexique (+, −, MIN, MAX)
    resultat: str
    unite: Literal["€", "jour"]


class Declaration(_Strict):
    genre: Literal["MEME", "DIFFERENT"]
    juste: bool
    faits: tuple[int, int]  # rangs des deux noms dans le message


class Element(_Strict):
    genre: Literal["MOTS", "M", "N", "CALCUL"]
    mots: str = ""
    fait: str = ""
    calcul: tuple[str, ...] = ()


class Phrase(_Strict):
    relation: str
    gabarit: str
    sources: tuple[str, ...]
    elements: tuple[Element, ...]
    texte: str  # rendu, pour la lecture


class Question(_Strict):
    id: str
    type: str
    sous_type: str
    historique: tuple[Tour, ...] = ()
    message: Tour
    etapes: tuple[Etape, ...] = ()
    identites: tuple[Identite, ...] = ()
    calcul: Calcul | None = None
    declaration: Declaration | None = None
    ambigus: tuple[str, ...] = ()  # un fait par personne possible (ASK_SAME)
    abstention: bool = False
    synthese: tuple[Phrase, ...] = ()

    @property
    def justificatives(self) -> tuple[str, ...]:
        return tuple(e.lignes[0] for e in self.etapes)


@cache
def gabarits_questions(reservoir: str) -> dict:
    with QUESTIONS_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)[reservoir]


_CHAMP = re.compile(r"\{(\w+)\}")
_OPTION = re.compile(r"\[([^\]]*)\]")
_CONTRACTION = re.compile(r"\b(de|à) les? ")


def _contracter(s: str) -> str:
    """« de le vol » → « du vol », « à le » → « au » (texte fixe seulement)."""
    table = {"de le ": "du ", "à le ": "au ", "de les ": "des ", "à les ": "aux "}
    return _CONTRACTION.sub(lambda m: table[m[0]], s)


def _liste(parties: list[list]) -> list:
    out: list = []
    for i, morceaux in enumerate(parties):
        if i:
            out.append((" et " if i == len(parties) - 1 else ", ", None))
        out += morceaux
    return out


class _Msg:
    """Champs d'un message en cours d'écriture : nom ou date → morceaux."""

    def __init__(self, poseur: "_Poseur"):
        self.p = poseur
        self.champs: dict[str, list] = {}

    def _ajout(self, morceaux: list) -> str:
        k = f"C{len(self.champs)}"
        self.champs[k] = morceaux
        return "{" + k + "}"

    def nom(self, genre: str, x: int, forme: str) -> str:
        return self._ajout(self.p.nom(genre, x, forme))

    def ambigu(self, surface: str, forme: str) -> str:
        return self._ajout([(surface, dict(genre="PER", entite=None, forme=forme))])

    def date(self, d) -> str:
        return self._ajout([(ecrire_date(d, self.p.rng), dict(genre="DATE", valeur=d.isoformat()))])


class _Poseur:
    def __init__(self, d: Dossier, cfg: WorldgenConfig):
        self.d, self.m, self.c = d, d.monde, cfg.questions
        self.rng = random.Random(f"questions-{self.m.graine}")
        self.g = gabarits_questions(self.m.reservoir)
        self.conf = d.conflit.evenement if d.conflit else None
        self.lignes = {f"{p.id}:{i}": x for p in d.pieces for i, x in enumerate(p.lignes)}
        self.par_ev: dict[tuple[int, int], list[str]] = defaultdict(list)
        for ref, x in self.lignes.items():
            if x.evenement is not None:
                self.par_ev[(x.evenement, x.version)].append(ref)
        self.versions = list(self.m.evenements) + ([d.variante] if d.variante else [])
        # Porteurs de chaque clé de nom : une clé univoque désigne une seule entité.
        self.porteurs: dict[tuple[str, str], set[int]] = defaultdict(set)
        for p in self.m.personnes:
            for f in FORMES_PER:
                if f != "SURNOM" or p.surnom:
                    self.porteurs[("PER", cle(forme_personne(p, f)))].add(p.id)
        for s in self.m.societes:
            for f in ("COMPLET", "COURT"):
                self.porteurs[("ORG", cle(forme_societe(s, f)))].add(s.id)
        self.preuves: dict[int, list[str]] = defaultdict(list)  # lignes « X, dit S »
        for ref, x in self.lignes.items():
            formes = defaultdict(set)
            for f in x.faits:
                if f.genre == "PER":
                    formes[f.entite].add(f.forme)
            for ent, fs in formes.items():
                if {"COMPLET", "SURNOM"} <= fs:
                    self.preuves[ent].append(ref)

    # --- Lecture des lignes --------------------------------------------------------------

    def normes(self, ref: str, genre: str, x: int) -> dict[str, tuple[int, str]]:
        """Clé → (rang du premier fait, forme) des noms de l'entité dans la ligne."""
        out: dict[str, tuple[int, str]] = {}
        for i, f in enumerate(self.lignes[ref].faits):
            if f.genre == genre and f.entite == x:
                out.setdefault(cle(f.surface), (i, f.forme))
        return out

    def noms(self, ref: str) -> set[tuple[str, str]]:
        return {
            (f.genre, cle(f.surface)) for f in self.lignes[ref].faits if f.genre in ("PER", "ORG")
        }

    def univoque(self, genre: str, n: str) -> bool:
        return len(self.porteurs.get((genre, n), ())) == 1

    def univoques(self, ref: str, genre: str, x: int) -> dict[str, tuple[int, str]]:
        return {n: v for n, v in self.normes(ref, genre, x).items() if self.univoque(genre, n)}

    def evenement(self, ref: str) -> Evenement:
        x = self.lignes[ref]
        return self.d.evenement(x.evenement, x.version)

    def porte(self, ref: str, attr: str) -> bool:
        faits = self.lignes[ref].faits
        if attr == "PERSONNE":
            ev = self.evenement(ref)
            presents = {f.entite for f in faits if f.genre == "PER"}
            return len(ev.participants) > 1 and set(ev.participants) <= presents
        return any(f.genre == GENRE_ATTRIBUT[attr] for f in faits)

    def attributs(self, e: Evenement, version: int = 0) -> list[str]:
        return [a for a in ATTRIBUTS if any(self.porte(r, a) for r in self.par_ev[(e.id, version)])]

    def choisir_lignes(self, e_id, fixes: dict, libres: list, attr=None, version=0, autres=()):
        """Lignes de l'événement qui nomment les entités `fixes` sous leur clé, les entités
        `libres` sous une clé univoque, et portent l'attribut. Rend (lignes, clés choisies) :
        la ligne préférée d'abord, puis les lignes équivalentes (mêmes clés)."""
        cands = [
            r
            for r in self.par_ev[(e_id, version)]
            if (attr is None or self.porte(r, attr))
            and all(n in self.normes(r, g, x) for (g, x), n in fixes.items())
            and all(self.univoques(r, g, x) for g, x in libres)
            and all(c(r) for c in autres)
        ]
        if not cands:
            return None
        pref = self.rng.choice(cands)
        choisies = {k: self.rng.choice(sorted(self.univoques(pref, *k))) for k in libres}
        tout = {**fixes, **choisies}
        alts = [r for r in cands if all(n in self.normes(r, g, x) for (g, x), n in tout.items())]
        return (pref, *[r for r in alts if r != pref]), choisies

    # --- Écriture des messages -----------------------------------------------------------

    def nom(self, genre: str, x: int, forme: str) -> list:
        fait = dict(genre=genre, entite=x, forme=forme)
        if genre == "ORG":
            s = self.m.societes[x]
            if forme == "COMPLET":
                return [("l'" if s.nom[0] in "AEIOU" else "la ", None), (s.nom, fait)]
            return [("la société ", None), (forme_societe(s, forme), fait)]
        p = self.m.personnes[x]
        if forme in ("NOM_SEUL", "TITRE_NOM"):
            fait["forme"] = "NOM_SEUL"
            if self.rng.random() < self.c.part_titre:
                titre = "Me" if p.role == "AVOCAT" else ("Mme" if p.genre == "F" else "M.")
                fait["forme"] = "TITRE_NOM"
                return [(f"{titre} ", None), (p.nom, fait)]
            return [(p.nom, fait)]
        return [(forme_personne(p, forme), fait)]

    def message(self, modele: str, msg: _Msg) -> Tour:
        morceaux: list = []
        for i, bout in enumerate(_CHAMP.split(_contracter(modele))):
            morceaux += msg.champs[bout] if i % 2 else [(bout, None)]
        texte, faits = assembler(morceaux)
        return Tour(role="UTILISATEUR", texte=texte, faits=tuple(faits))

    def identifiable(self, e: Evenement, genre: str, x: int, date_permise: bool):
        """None : ambigu ; False : décrit sans date ; True : décrit avec sa date."""
        cle_ = "participants" if genre == "PER" else "societes"
        ids = {v.id for v in self.versions if v.type == e.type and x in getattr(v, cle_)}
        if ids == {e.id}:
            return False
        if date_permise and {i for i in ids if self.m.evenements[i].date == e.date} == {e.id}:
            return True
        return None

    def decrire(self, msg: _Msg, e: Evenement, genre: str, x: int, date_permise: bool, X: str):
        """Description de l'événement par l'entité X (placeholder ou relais)."""
        ident = self.identifiable(e, genre, x, date_permise)
        if ident is None:
            return None
        ident = ident or (date_permise and self.rng.random() < self.c.part_date)
        cle_ = "evenements" if genre == "PER" else "evenements_societe"
        s = self.rng.choice(self.g[cle_][e.type]).replace("{X}", X)
        if ident:
            s += self.rng.choice(self.g["qualif_date"]).replace("{D}", msg.date(e.date))
        return s

    def ancre(self, e: Evenement, attr, version=0, autres=(), exclus=(), genre=None):
        """(genre, entité, clé, forme, lignes) : entité nommée par la question."""
        if genre is None:
            societe = e.societes and attr != "SOCIETE" and e.type in self.g["evenements_societe"]
            genre = "ORG" if societe and self.rng.random() < self.c.part_societe else "PER"
        if genre == "PER":
            ents = [x for x in e.participants if x not in exclus]
        else:
            ents = list(e.societes)
        self.rng.shuffle(ents)
        for x in ents:
            r = self.choisir_lignes(e.id, {}, [(genre, x)], attr, version, autres)
            if r:
                refs, cles = r
                n = cles[(genre, x)]
                return genre, x, n, self.normes(refs[0], genre, x)[n][1], refs
        return None

    def tirer_evenement(self, filtre=lambda e: True) -> Evenement | None:
        evs = [e for e in self.m.evenements if e.id != self.conf and filtre(e)]
        return self.rng.choice(evs) if evs else None

    def question_attribut(self, e: Evenement, attr: str, msg: _Msg, genre=None, autres=()):
        """Question sur un attribut de e : (modèle, lignes, entité)."""
        an = self.ancre(e, attr, autres=autres, genre=genre)
        if an is None:
            return None
        genre, x, _, forme, refs = an
        E = self.decrire(msg, e, genre, x, attr != "DATE", msg.nom(genre, x, forme))
        if E is None:
            return None
        return self.rng.choice(self.g["attributs"][attr]).replace("{E}", E), refs, (genre, x)

    # --- Synthèse ------------------------------------------------------------------------

    def phrase(self, relation: str, sources, champs: dict) -> "Phrase | None":
        def possible(m: str) -> bool:
            return all(c in champs for c in _CHAMP.findall(_OPTION.sub("", m)))

        modeles = [(i, m) for i, m in enumerate(self.g["synthese"][relation]) if possible(m)]
        if not modeles:
            return None
        i, modele = self.rng.choice(modeles)
        morceaux: list = []
        for j, part in enumerate(_OPTION.split(modele)):
            if j % 2 and not all(c in champs for c in _CHAMP.findall(part)):
                continue
            for k, bout in enumerate(_CHAMP.split(part)):
                morceaux += champs[bout] if k % 2 else [(bout, None)] if bout else []
        return Phrase(
            relation=relation,
            gabarit=f"synthese/{relation}/{i}",
            sources=tuple(sources),
            **_elements(morceaux),
        )

    def pointeur(self, ref: str, i: int) -> tuple:
        f = self.lignes[ref].faits[i]
        return (f.surface, Element(genre=POINTEUR[f.genre], fait=f"{ref}:{i}"))

    def champs_ligne(self, ref: str) -> dict:
        x, ev = self.lignes[ref], self.evenement(ref)
        per, nums, champs, vus = [], [], {}, set()
        for i, f in enumerate(x.faits):
            if f.genre == "PER" and f.entite in ev.participants and f.entite not in vus:
                vus.add(f.entite)
                per.append([self.pointeur(ref, i)])
            elif f.genre == "NUM":
                nums.append([self.pointeur(ref, i)])
            elif f.genre == "LIEU" and "L" not in champs:
                prep = "au " if self.m.lieux[f.entite].genre == "ADRESSE" else "à "
                champs["L"] = [(prep, None), self.pointeur(ref, i)]
            elif f.genre in ("ORG", "DATE", "HEURE"):
                champs.setdefault(
                    {"ORG": "S", "DATE": "D", "HEURE": "H"}[f.genre], [self.pointeur(ref, i)]
                )
        if per:
            champs["P"] = _liste(per)
            champs["a"] = [("a" if len(per) == 1 else "ont", None)]
        if nums:
            champs["M"] = _liste(nums)
        return champs

    def s_evenement(self, ref: str, final: bool = True) -> list:
        champs = self.champs_ligne(ref)
        out = [self.phrase(self.evenement(ref).type, [ref], champs)]
        if final:
            out.append(self.phrase("CIRCONSTANCES", [ref], champs))
        return [p for p in out if p]

    # --- Types de questions --------------------------------------------------------------

    def fait_simple(self):
        e = self.tirer_evenement()
        if e is None or not self.attributs(e):
            return None
        attr = self.rng.choice(self.attributs(e))
        msg = _Msg(self)
        q = self.question_attribut(e, attr, msg)
        if q is None:
            return None
        modele, refs, _ = q
        return dict(
            sous_type=attr,
            message=self.message(modele, msg),
            etapes=(Etape(role="CITE", lignes=refs),),
            synthese=tuple(self.s_evenement(refs[0])),
        )

    def plusieurs_etapes(self):
        k = self.rng.choices(list(self.c.etapes), list(self.c.etapes.values()))[0]
        duo = [e for e in self.m.evenements if e.id != self.conf and len(e.participants) == 2]
        if not duo:
            return None
        e1 = self.rng.choice(duo)
        x0 = self.rng.choice(e1.participants)
        evs, pers = [e1], [x0, next(x for x in e1.participants if x != x0)]
        for _ in range(k - 2):
            suite = [
                e
                for e in duo
                if pers[-1] in e.participants
                and e not in evs
                and e.type != evs[-1].type
                and all(x not in pers[:-1] for x in e.participants)
            ]
            if not suite:
                return None
            e = self.rng.choice(suite)
            evs.append(e)
            pers.append(next(x for x in e.participants if x != pers[-1]))
        fin = self.tirer_evenement(
            lambda e: pers[-1] in e.participants and e not in evs and e.type != evs[-1].type
        )
        if fin is None or not self.attributs(fin):
            return None
        attr = self.rng.choice(self.attributs(fin))

        # Lignes : chaque personne relais garde la même clé d'une étape à la suivante.
        fixes, etapes = {}, []
        for i, e in enumerate(evs):
            libres = [("PER", x) for x in (pers[i], pers[i + 1]) if ("PER", x) not in fixes]
            r = self.choisir_lignes(
                e.id, {("PER", pers[i]): fixes[("PER", pers[i])]} if i else {}, libres
            )
            if r is None:
                return None
            fixes.update(r[1])
            etapes.append(r[0])
        r = self.choisir_lignes(fin.id, {("PER", pers[-1]): fixes[("PER", pers[-1])]}, [], attr)
        if r is None:
            return None
        etapes.append(r[0])

        msg = _Msg(self)
        forme0 = self.normes(etapes[0][0], "PER", x0)[fixes[("PER", x0)]][1]
        X = msg.nom("PER", x0, forme0)
        for i, e in enumerate(evs):
            ident = self.identifiable(e, "PER", pers[i], True)
            if ident is None:
                return None
            X = self.rng.choice(self.g["relais"][e.type]).replace("{X}", X)
            if ident:
                X += self.rng.choice(self.g["qualif_date"]).replace("{D}", msg.date(e.date))
        E = self.decrire(msg, fin, "PER", pers[-1], attr != "DATE", X)
        if E is None:
            return None
        synthese = [p for refs in etapes[:-1] for p in self.s_evenement(refs[0], final=False)]
        return dict(
            sous_type=f"{k}_ETAPES",
            message=self.message(self.rng.choice(self.g["attributs"][attr]).replace("{E}", E), msg),
            etapes=tuple(Etape(role="CITE", lignes=refs) for refs in etapes),
            synthese=tuple(synthese + self.s_evenement(etapes[-1][0])),
        )

    def options_identite(self, e: Evenement, attr: str, x: int, preuve: bool):
        """(ligne, clé dans la ligne, forme de la question, preuves) : la ligne nomme x
        autrement que la question. Avec preuve : surnom contre nom complet."""
        p = self.m.personnes[x]
        out = []
        for r in self.par_ev[(e.id, 0)]:
            if not self.porte(r, attr):
                continue
            normes = self.normes(r, "PER", x)
            for n_l, (_, forme_l) in self.univoques(r, "PER", x).items():
                if forme_l == "SURNOM":
                    formes = ["COMPLET"]
                elif forme_l == "COMPLET":
                    formes = ["NOM_PRENOM"] + (["SURNOM"] if p.surnom else [])
                else:
                    formes = ["COMPLET"]
                for forme_q in formes:
                    n_q = cle(forme_personne(p, forme_q))
                    a_preuve = "SURNOM" in (forme_l, forme_q)
                    if preuve is not None and a_preuve != preuve:
                        continue
                    if n_q in normes or not self.univoque("PER", n_q):
                        continue
                    if a_preuve and preuve and not self.preuves[x]:
                        continue
                    out.append((r, n_l, forme_q, n_q))
        return out

    def identite(self, declaration: bool = False):
        preuve = None if declaration else self.rng.random() < self.c.part_preuve
        # Avec preuve : une personne à surnom, nommée « X, dit S » dans une ligne au moins.
        filtre = (lambda e: any(self.preuves[x] for x in e.participants)) if preuve else None
        e = self.tirer_evenement(filtre or (lambda e: True))
        if e is None or not self.attributs(e):
            return None
        attr = self.rng.choice(self.attributs(e))
        x = self.rng.choice([x for x in e.participants if self.preuves[x] or not preuve])
        options = self.options_identite(e, attr, x, preuve)
        if not options:
            return None
        pref, n_l, forme_q, n_q = self.rng.choice(options)
        alts = [
            r
            for r in self.par_ev[(e.id, 0)]
            if r != pref
            and self.porte(r, attr)
            and n_l in self.normes(r, "PER", x)
            and n_q not in self.normes(r, "PER", x)
        ]
        i_l, forme_l = self.normes(pref, "PER", x)[n_l]
        msg = _Msg(self)
        Xq = msg.nom("PER", x, forme_q)
        E = self.decrire(msg, e, "PER", x, attr != "DATE", Xq)
        if E is None:
            return None
        modele = self.rng.choice(self.g["attributs"][attr]).replace("{E}", E)
        etapes, synthese = [], []
        if declaration:
            decl = self.rng.choice(self.g["declarations"]["MEME"])
            modele = (
                decl.replace("{X}", Xq).replace("{Y}", msg.nom("PER", x, forme_l)) + " " + modele
            )
        elif preuve:
            preuves = self.preuves[x][:]
            self.rng.shuffle(preuves)
            etapes.append(Etape(role="PREUVE", lignes=tuple(preuves)))
            faits = list(enumerate(self.lignes[preuves[0]].faits))
            champs = {
                k: [self.pointeur(preuves[0], next(i for i, f in faits if self._de(f, x, fo)))]
                for k, fo in (("X", "COMPLET"), ("Y", "SURNOM"))
            }
            synthese.append(self.phrase("ALIAS", [preuves[0]], champs))
        else:
            synthese.append(self.phrase("RESSEMBLANCE", [pref], {"Y": [self.pointeur(pref, i_l)]}))
        etapes.append(Etape(role="CITE", lignes=(pref, *alts)))
        message = self.message(modele, msg)
        # Premier rang de chaque forme de x dans le message.
        rang = {f.forme: i for i, f in reversed(list(enumerate(message.faits))) if f.entite == x}
        out = dict(
            message=message,
            etapes=tuple(etapes),
            synthese=tuple(p for p in synthese + self.s_evenement(pref) if p),
        )
        if declaration:
            autre = next(f for f in rang if f != forme_q)
            out["declaration"] = Declaration(
                genre="MEME", juste=True, faits=tuple(sorted((rang[forme_q], rang[autre])))
            )
            out["sous_type"] = "NOTE_SAME"
        else:
            pr = etapes[0].lignes[0] if preuve else None
            out["identites"] = (Identite(question=rang[forme_q], fait=f"{pref}:{i_l}", preuve=pr),)
            out["sous_type"] = f"{'PREUVE' if preuve else 'RESSEMBLANCE'}_{forme_l}"
        return out

    @staticmethod
    def _de(f: Fait, x: int, forme: str) -> bool:
        return f.genre == "PER" and f.entite == x and f.forme == forme

    def fait_absent(self):
        msg = _Msg(self)
        if self.rng.random() < 0.5:  # attribut que les pièces ne donnent pas
            e = self.tirer_evenement()
            if e is None:
                return None
            refs = self.par_ev[(e.id, 0)] + self.par_ev[(e.id, 1)]
            manquants = [a for a in ("HEURE", "LIEU") if not any(self.porte(r, a) for r in refs)]
            if not manquants:
                return None
            attr = self.rng.choice(manquants)
            an = self.ancre(e, None)
            if an is None:
                return None
            genre, x, _, forme, _ = an
            E = self.decrire(msg, e, genre, x, True, msg.nom(genre, x, forme))
            sous_type = f"ATTRIBUT_{attr}"
        else:  # événement que les pièces ne rapportent pas
            noms = [
                (f.entite, f.forme)
                for x in self.lignes.values()
                for f in x.faits
                if f.genre == "PER" and self.univoque("PER", cle(f.surface))
            ]
            if not noms:
                return None
            x, forme = self.rng.choice(noms)
            faits = {v.type for v in self.versions if x in v.participants}
            types = [t for t in self.g["evenements"] if t not in faits]
            if not types:
                return None
            attr = self.rng.choice(("DATE", "LIEU", "HEURE"))
            modele = self.rng.choice(self.g["evenements"][self.rng.choice(types)])
            E = modele.replace("{X}", msg.nom("PER", x, forme))
            sous_type = "EVENEMENT"
        if E is None:
            return None
        modele = self.rng.choice(self.g["attributs"][attr]).replace("{E}", E)
        return dict(sous_type=sous_type, message=self.message(modele, msg), abstention=True)

    def conflit(self):
        k = self.d.conflit
        if k is None:
            return None
        e0, e1 = self.m.evenements[k.evenement], self.d.variante
        if k.champ == "HEURE":
            change = [lambda f: f.genre == "HEURE"] * 2
        elif k.champ == "MONTANT":
            a, b = set(e0.montants) - set(e1.montants), set(e1.montants) - set(e0.montants)
            change = [lambda f, s=s: f.genre == "NUM" and Decimal(f.valeur) in s for s in (a, b)]
        else:
            a, b = (
                set(e0.participants) - set(e1.participants),
                set(e1.participants) - set(e0.participants),
            )
            change = [lambda f, s=s: f.genre == "PER" and f.entite in s for s in (a, b)]

        def portant(v):
            return lambda r: any(change[v](f) for f in self.lignes[r].faits)

        attrs = [k.champ] * 3 + [a for a in self.attributs(e0) if a not in (k.champ, "PERSONNE")]
        attr = self.rng.choice(attrs)
        commun = set(e0.participants) & set(e1.participants)
        an = self.ancre(
            e0, attr, version=0, autres=[portant(0)], exclus=set(e0.participants) - commun
        )
        msg = _Msg(self)
        par_date = an is None or self.rng.random() < self.c.part_conflit_date
        if par_date:
            # Événement désigné par son type et sa date, sans nom : la version contradictoire
            # peut nommer autrement (ou remplacer) toutes les personnes.
            if attr == "DATE" or {
                v.id for v in self.versions if (v.type, v.date) == (e0.type, e0.date)
            } != {e0.id}:
                return None
            refs0 = [r for r in self.par_ev[(e0.id, 0)] if self.porte(r, attr) and portant(0)(r)]
            refs1 = [r for r in self.par_ev[(e0.id, 1)] if self.porte(r, attr) and portant(1)(r)]
            E = self.rng.choice(self.g["par_date"][e0.type]).replace("{D}", msg.date(e0.date))
        else:
            genre, x, n, forme, refs0 = an
            # La version contradictoire se relie à la ligne préférée par un nom identique (§11).
            noms0 = self.noms(refs0[0])
            refs1 = [
                r
                for r in self.par_ev[(e0.id, 1)]
                if self.porte(r, attr) and portant(1)(r) and self.noms(r) & noms0
            ]
            E = self.decrire(msg, e0, genre, x, attr != "DATE", msg.nom(genre, x, forme))
        if not refs0 or not refs1 or E is None:
            return None
        refs0, refs1 = list(refs0), list(refs1)
        if par_date:  # sinon refs0[0] est la ligne à laquelle refs1 se relie
            self.rng.shuffle(refs0)
        self.rng.shuffle(refs1)
        champs = {}
        for v, ref in ((0, refs0[0]), (1, refs1[0])):
            i = next(i for i, f in enumerate(self.lignes[ref].faits) if change[v](f))
            champs[f"V{v}"] = [self.pointeur(ref, i)]
        synthese = self.s_evenement(refs0[0], False) + self.s_evenement(refs1[0], False)
        synthese.append(self.phrase("CONFLIT", [refs0[0], refs1[0]], champs))
        modele = self.rng.choice(self.g["attributs"][attr]).replace("{E}", E)
        return dict(
            sous_type=f"{k.champ}_{attr}",
            message=self.message(modele, msg),
            etapes=(Etape(role="CONFLIT", lignes=refs0), Etape(role="CONFLIT", lignes=refs1)),
            synthese=tuple(p for p in synthese if p),
        )

    def calcul(self):
        op = self.rng.choice(self.c.calculs)
        if op == "SOMME" and self.rng.random() < self.c.part_somme_une:
            return self.somme_une()
        n = self.rng.choice((2, 3)) if op in ("MIN", "MAX") else 2
        attr = "DATE" if op == "DUREE" else "MONTANT"
        evs = [
            e
            for e in self.m.evenements
            if e.id != self.conf and (op == "DUREE" or len(e.montants) == 1)
        ]
        if len(evs) < n:
            return None
        evs = self.rng.sample(evs, n)
        cle_v = (lambda e: e.date) if op == "DUREE" else (lambda e: e.montants[0])
        if len({cle_v(e) for e in evs}) < n:
            return None
        msg, descs, operandes, etapes = _Msg(self), [], [], []
        for e in evs:
            an = self.ancre(e, attr)
            if an is None:
                return None
            genre, x, _, forme, refs = an
            E = self.decrire(msg, e, genre, x, op != "DUREE", msg.nom(genre, x, forme))
            if E is None:
                return None
            descs.append(E)
            etapes.append(refs)
            i = next(
                i
                for i, f in enumerate(self.lignes[refs[0]].faits)
                if f.genre == GENRE_ATTRIBUT[attr]
            )
            operandes.append((cle_v(e), f"{refs[0]}:{i}"))
        if op in ("ECART", "DUREE"):
            operandes.sort(reverse=True)  # plus grand (ou plus tard) d'abord
        symbole = {"SOMME": "+", "ECART": "−", "DUREE": "−", "MIN": "MIN", "MAX": "MAX"}[op]
        postfixe = [operandes[0][1]]
        for _, f in operandes[1:]:
            postfixe += [f, symbole]
        valeurs = [v for v, _ in operandes]
        if op == "DUREE":
            resultat, unite = str((valeurs[0] - valeurs[1]).days), "jour"
        else:
            r = {
                "SOMME": sum(valeurs),
                "ECART": valeurs[0] - valeurs[1],
                "MIN": min(valeurs),
                "MAX": max(valeurs),
            }[op]
            resultat, unite = str(r.quantize(Decimal("0.01"))), "€"
        if op in ("MIN", "MAX"):
            modele = self.rng.choice(self.g["calculs"][op]).replace("{EL}", _liste_texte(descs))
        else:
            modele = self.rng.choice(self.g["calculs"][op])
            modele = modele.replace("{E1}", descs[0]).replace("{E2}", descs[1])
        return self._calcul(op, msg, modele, etapes, postfixe, resultat, unite, op)

    def somme_une(self):
        def complet(r):
            return sum(f.genre == "NUM" for f in self.lignes[r].faits) == len(
                self.evenement(r).montants
            )

        e = self.tirer_evenement(lambda e: len(e.montants) > 1)
        if e is None:
            return None
        an = self.ancre(e, "MONTANT", autres=[complet])
        if an is None:
            return None
        genre, x, _, forme, refs = an
        msg = _Msg(self)
        E = self.decrire(msg, e, genre, x, True, msg.nom(genre, x, forme))
        if E is None:
            return None
        modele = self.rng.choice(self.g["calculs"]["SOMME_UNE"]).replace("{E}", E)
        nums = [i for i, f in enumerate(self.lignes[refs[0]].faits) if f.genre == "NUM"]
        postfixe = [f"{refs[0]}:{nums[0]}"]
        for i in nums[1:]:
            postfixe += [f"{refs[0]}:{i}", "+"]
        resultat = str(sum(e.montants).quantize(Decimal("0.01")))
        return self._calcul("SOMME", msg, modele, [refs], postfixe, resultat, "€", "SOMME_UNE")

    def _calcul(self, op, msg, modele, etapes, postfixe, resultat, unite, sous_type):
        if unite == "€":
            texte = f"{Decimal(resultat):,.2f} €".replace(",", " ").replace(".", ",")
        else:
            texte = f"{resultat} jours"
        c = (texte, Element(genre="CALCUL", calcul=tuple(postfixe)))
        synthese = [p for refs in etapes for p in self.s_evenement(refs[0], False)]
        synthese.append(self.phrase(op, [refs[0] for refs in etapes], {"C": [c]}))
        return dict(
            sous_type=sous_type,
            message=self.message(modele, msg),
            etapes=tuple(Etape(role="CITE", lignes=refs) for refs in etapes),
            calcul=Calcul(operation=op, postfixe=tuple(postfixe), resultat=resultat, unite=unite),
            synthese=tuple(p for p in synthese if p),
        )

    def dialogue(self):
        sous = self.rng.choices(list(self.c.dialogues), list(self.c.dialogues.values()))[0]
        out = getattr(self, f"d_{sous.lower()}")()
        if out is not None:
            out.setdefault("sous_type", sous)
        return out

    def d_suite(self):
        e = self.tirer_evenement()
        if e is None or len(self.attributs(e)) < 2:
            return None
        a1, a2 = self.rng.sample(self.attributs(e), 2)
        an = self.ancre(e, a1, genre="PER")
        if an is None:
            return None
        _, x, n, forme, refs1 = an
        r = self.choisir_lignes(e.id, {("PER", x): n}, [], a2)
        if r is None:
            return None
        msg = _Msg(self)
        E = self.decrire(msg, e, "PER", x, "DATE" not in (a1, a2), msg.nom("PER", x, forme))
        if E is None:
            return None
        avant = self.message(self.rng.choice(self.g["attributs"][a1]).replace("{E}", E), msg)
        il, lui = ("elle", "elle") if self.m.personnes[x].genre == "F" else ("il", "lui")
        texte = self.rng.choice(self.g["suites"][a2]).replace("{il}", il).replace("{lui}", lui)
        refs = r[0]
        return dict(
            historique=(avant, Tour(role="MODELE", lignes=(refs1[0],))),
            message=Tour(role="UTILISATEUR", texte=texte),
            etapes=(Etape(role="CITE", lignes=refs),),
            synthese=tuple(self.s_evenement(refs[0])),
        )

    def d_note_same(self):
        return self.identite(declaration=True)

    def d_note_diff(self):
        e = self.tirer_evenement()
        if e is None or not self.attributs(e):
            return None
        attr = self.rng.choice(self.attributs(e))
        msg = _Msg(self)
        q = self.question_attribut(e, attr, msg, genre="PER")
        if q is None:
            return None
        modele, refs, (_, x) = q
        p = self.m.personnes[x]

        def complet_univoque(y):
            return self.univoque("PER", cle(forme_personne(self.m.personnes[y], "COMPLET")))

        autres = [y.id for y in self.m.personnes if y.id != x and complet_univoque(y.id)]
        proches = [y for y in autres if cle(self.m.personnes[y].nom) == cle(p.nom)]
        if not autres or not complet_univoque(x):
            return None
        y = self.rng.choice(proches or autres)
        decl = self.rng.choice(self.g["declarations"]["DIFFERENT"])
        decl = decl.replace("{X}", msg.nom("PER", x, "COMPLET")).replace(
            "{Y}", msg.nom("PER", y, "COMPLET")
        )
        message = self.message(decl + " " + modele, msg)
        return dict(
            message=message,
            etapes=(Etape(role="CITE", lignes=refs),),
            declaration=Declaration(genre="DIFFERENT", juste=True, faits=(0, 1)),
            synthese=tuple(self.s_evenement(refs[0])),
        )

    def d_declaration_fausse(self):
        e = self.tirer_evenement(lambda e: len(e.participants) > 1)
        if e is None or not self.attributs(e):
            return None
        attr = self.rng.choice(self.attributs(e))
        a, b = self.rng.sample(e.participants, 2)
        r = self.choisir_lignes(e.id, {}, [("PER", a), ("PER", b)], attr)
        if r is None:
            return None
        refs, cles = r
        fa = self.normes(refs[0], "PER", a)[cles[("PER", a)]]
        fb = self.normes(refs[0], "PER", b)[cles[("PER", b)]]
        msg = _Msg(self)
        Xa = msg.nom("PER", a, fa[1])
        E = self.decrire(msg, e, "PER", a, attr != "DATE", Xa)
        if E is None:
            return None
        decl = self.rng.choice(self.g["declarations"]["MEME"])
        decl = decl.replace("{X}", Xa).replace("{Y}", msg.nom("PER", b, fb[1]))
        modele = decl + " " + self.rng.choice(self.g["attributs"][attr]).replace("{E}", E)
        champs = {"X": [self.pointeur(refs[0], fa[0])], "Y": [self.pointeur(refs[0], fb[0])]}
        synthese = [self.phrase("DISTINCTS", [refs[0]], champs)] + self.s_evenement(refs[0])
        return dict(
            message=self.message(modele, msg),
            etapes=(Etape(role="CITE", lignes=refs),),
            declaration=Declaration(genre="MEME", juste=False, faits=(0, 1)),
            synthese=tuple(p for p in synthese if p),
        )

    def d_ask_same(self):
        """Un nom seul ou des initiales que portent plusieurs personnes : ASK_SAME."""
        groupes = []
        for forme in ("NOM_SEUL", "INITIALES"):
            par: dict[str, list[int]] = defaultdict(list)
            for p in self.m.personnes:
                par[cle(forme_personne(p, forme))].append(p.id)
            for xs in par.values():
                complets = {cle(forme_personne(self.m.personnes[x], "COMPLET")) for x in xs}
                if len(xs) > 1 and len(complets) == len(xs):  # pas d'homonymes exacts
                    groupes.append((forme, xs))
        if not groupes:
            return None
        forme, xs = self.rng.choice(groupes)
        surface = forme_personne(self.m.personnes[xs[0]], forme)
        e = self.tirer_evenement(lambda e: any(x in e.participants for x in xs))
        if e is None or not self.attributs(e):
            return None
        attr = self.rng.choice(self.attributs(e))
        ambigus = []
        for x in xs:
            refs = [
                r
                for v in self.m.evenements
                if x in v.participants and v.type == e.type
                for r in self.par_ev[(v.id, 0)]
            ]
            refs += [r for r in self.lignes if r not in refs]
            fait = next(
                (f"{r}:{i}" for r in refs for _, (i, _) in self.univoques(r, "PER", x).items()),
                None,
            )
            if fait:
                ambigus.append(fait)
        if len(ambigus) < 2:
            return None
        msg = _Msg(self)
        modele = self.rng.choice(self.g["evenements"][e.type]).replace(
            "{X}", msg.ambigu(surface, forme)
        )
        modele = self.rng.choice(self.g["attributs"][attr]).replace("{E}", modele)
        return dict(message=self.message(modele, msg), ambigus=tuple(ambigus))

    # --- Dossier -------------------------------------------------------------------------

    def poser(self) -> tuple[Question, ...]:
        """Conflits d'abord (dossiers à versions contradictoires seulement) ; le reste du
        dossier se partage entre les autres types selon leurs parts, arrondi au hasard."""
        out: list[Question] = []
        vus: set[tuple[str, ...]] = set()
        n_conf = self.c.conflit_par_dossier if self.d.conflit else 0
        self._remplir("CONFLIT", n_conf, out, vus)
        autres = {t: v for t, v in self.c.parts.items() if t != "CONFLIT"}
        total = sum(autres.values())
        reste = self.c.par_dossier - len(out)
        quotas = {}
        for t in TYPES:
            if t in autres:
                x = reste * autres[t] / total
                quotas[t] = int(x) + (self.rng.random() < x - int(x))
        for t, n in quotas.items():
            self._remplir(t, n, out, vus)
        return tuple(out)

    def _remplir(self, t: str, quota: int, out: list, vus: set) -> None:
        n = essais = 0
        while n < quota and essais < self.c.essais:
            essais += 1
            r = getattr(self, t.lower())()
            if r is None:
                continue
            cle_ = tuple(h.texte for h in r.get("historique", ())) + (r["message"].texte,)
            if cle_ in vus:
                continue
            vus.add(cle_)
            n += 1
            out.append(Question(id=f"{self.d.id}-q{len(out):02d}", type=t, **r))


def _liste_texte(parties: list[str]) -> str:
    if len(parties) == 1:
        return parties[0]
    return ", ".join(parties[:-1]) + " et " + parties[-1]


def _elements(morceaux: list) -> dict:
    """Éléments d'une phrase de synthèse (mots et pointeurs), élisions, majuscule initiale."""
    items: list[list] = []  # [texte, élément ou None]
    for s, el in morceaux:
        if el is None:
            s = _ELISION.sub(r"\1'", s)
            if items and items[-1][1] is None:
                items[-1][0] += s
                continue
        elif s[:1] in _VOYELLES and items and items[-1][1] is None:
            items[-1][0] = re.sub(r"\b([QqDd]u?)e $", r"\1'", items[-1][0])
        items.append([s, el])
    if items and items[0][1] is None:
        items[0][0] = items[0][0][0].upper() + items[0][0][1:]
    elements = tuple(Element(genre="MOTS", mots=s) if el is None else el for s, el in items)
    return dict(elements=elements, texte="".join(s for s, _ in items))


def poser_questions(d: Dossier, cfg: WorldgenConfig) -> tuple[Question, ...]:
    """Questions d'un dossier. Même dossier, même config : mêmes questions."""
    return _Poseur(d, cfg).poser()


# --- Contrôle ----------------------------------------------------------------------------

_MOT = re.compile(r"[^\W\d_]+(?:'|’)?|\d+|[^\s\w]")


def mots_interdits() -> frozenset[str]:
    r = _reservoirs()
    noms = {s.lower() for k in ("prenoms_m", "prenoms_f", "noms") for s in r[k]}
    return NEGATIONS | NOMBRES | JOURS | frozenset(MOIS) | frozenset(noms)


def controler_phrase(ph: Phrase, citees: set[str], lignes: dict, interdits=None) -> list[str]:
    """Règles du masque en mode synthèse (§10 bis) sur une phrase de référence."""
    interdits = mots_interdits() if interdits is None else interdits
    err = []
    if not 1 <= len(ph.sources) <= 4 or len(set(ph.sources)) != len(ph.sources):
        err.append("sources : 1 à 4, distinctes")
    if not set(ph.sources) <= citees:
        err.append("source non citée")
    pointeurs, mots = 0, 0
    for k, el in enumerate(ph.elements):
        if el.genre == "MOTS":
            for m in _MOT.findall(el.mots):
                mots += m[0].isalnum()
                base = m.rstrip("'’").lower()
                if m.isdigit() or base in interdits or (base == "n" and m.endswith("'")):
                    err.append(f"mot refusé : {m!r}")
                if m[0].isupper() and (k or mots > 1):
                    err.append(f"majuscule hors début : {m!r}")
                if len(base) > 1 and m.isupper():
                    err.append(f"sigle : {m!r}")
            continue
        mots += 1
        pointeurs += 1
        faits = [el.fait] if el.genre != "CALCUL" else [x for x in el.calcul if ":" in x]
        for ref in faits:
            ligne, _, i = ref.rpartition(":")
            if ligne not in ph.sources:
                err.append(f"pointeur hors des sources : {ref}")
                continue
            f = lignes[ligne].faits[int(i)]
            attendu = {"M": ("PER", "ORG", "LIEU"), "N": ("NUM", "DATE", "HEURE")}
            if el.genre in attendu and f.genre not in attendu[el.genre]:
                err.append(f"pointeur {el.genre} vers un fait {f.genre}")
    if not pointeurs:
        err.append("aucun pointeur")
    if mots > 40:
        err.append("plus de 40 mots")
    return err


def controler_questions(d: Dossier, questions) -> list[str]:
    """Vérité terrain cohérente avec les pièces : lignes, faits, ancrage, calculs,
    conflits, abstentions et règles du masque de la synthèse."""
    lignes = {f"{p.id}:{i}": x for p in d.pieces for i, x in enumerate(p.lignes)}
    interdits = mots_interdits()
    err = []
    for q in questions:
        e = []
        refs = [r for et in q.etapes for r in et.lignes]
        if any(r not in lignes for r in refs):
            err.append(f"{q.id} : ligne inconnue")
            continue
        sans_etape = q.abstention or q.ambigus
        if bool(sans_etape) == bool(q.etapes) or (sans_etape and q.synthese):
            e.append("abstention incohérente")
        # Ancrage : chaque citation nomme un nom déjà lié à la question (§11).
        connus = {cle(f.surface) for t in (*q.historique, q.message) for f in t.faits}
        nomme = any(f.genre in ("PER", "ORG") for t in (*q.historique, q.message) for f in t.faits)
        if q.declaration and q.declaration.genre == "MEME":
            connus |= {cle(q.message.faits[i].surface) for i in q.declaration.faits}
        for idt in q.identites:
            ligne, _, i = idt.fait.rpartition(":")
            connus.add(cle(lignes[ligne].faits[int(i)].surface))
        for et in q.etapes:
            for r in et.lignes:
                noms = {cle(f.surface) for f in lignes[r].faits if f.genre in ("PER", "ORG")}
                if nomme and not noms & connus:  # règle sans objet sans nom (§11)
                    e.append(f"ligne non ancrée : {r}")
            connus |= {
                cle(f.surface) for f in lignes[et.lignes[0]].faits if f.genre in ("PER", "ORG")
            }
        if q.type == "CONFLIT":
            e += _controler_conflit(d, q, lignes)
        if q.calcul:
            e += _controler_calcul(q.calcul, lignes)
        if len(q.synthese) > 8:
            e.append("plus de 8 phrases")
        citees = set(q.justificatives)
        for ph in q.synthese:
            e += [f"{ph.gabarit} : {x}" for x in controler_phrase(ph, citees, lignes, interdits)]
        err += [f"{q.id} : {x}" for x in e]
    return err


def _controler_conflit(d: Dossier, q: Question, lignes: dict) -> list[str]:
    a, b = q.etapes
    if not d.conflit:
        return ["conflit sans version contradictoire"]
    if {lignes[r].version for r in a.lignes} != {0} or {lignes[r].version for r in b.lignes} != {1}:
        return ["versions des lignes en conflit"]
    champ = {"HEURE": "HEURE", "MONTANT": "NUM", "PER": "PER", "PERSONNE": "PER"}[d.conflit.champ]

    def valeurs(r):
        return {f.valeur or f.entite for f in lignes[r].faits if f.genre == champ}

    if any(valeurs(r0) == valeurs(r1) for r0 in a.lignes for r1 in b.lignes):
        return ["lignes en conflit de même valeur"]
    return []


def _controler_calcul(c: Calcul, lignes: dict) -> list[str]:
    pile: list = []
    for x in c.postfixe:
        if ":" in x:
            ligne, _, i = x.rpartition(":")
            f = lignes[ligne].faits[int(i)]
            pile.append(Decimal(f.valeur) if f.genre == "NUM" else _date(f.valeur))
            continue
        b, a = pile.pop(), pile.pop()
        pile.append({"+": add, "−": sub, "MIN": min, "MAX": max}[x](a, b))
    (r,) = pile
    r = str(r.days) if hasattr(r, "days") else str(r.quantize(Decimal("0.01")))
    return [] if r == c.resultat else [f"calcul faux : {r} ≠ {c.resultat}"]


def _date(iso: str):
    from datetime import date

    return date.fromisoformat(iso)
