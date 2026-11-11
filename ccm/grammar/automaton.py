"""Automate de sortie et règles du masque (SPEC.md §10, §10 bis).

À chaque pas, `Automate.autorises()` donne l'ensemble des pas permis ; le même automate
prépare les données, décode et relit la sortie. Pas : jeton du lexique, pointeur « P:k »
(proposition locale k), « M:t.j » (marque j du texte t : « q », « h1 »…, ou k), « N:t.j »
(nombre), mot « W:mot » (synthèse).

Aucune impasse : un pas n'est permis que si la réponse peut encore finir, dans la limite
de pas (`pas_max`, ou `pas_max_synthese` en mode synthèse). Chaque ouverture de segment
vérifie qu'il peut se fermer ; un CALCUL garde une pile réductible (§10, algèbre des
unités, avec les vraies valeurs).
"""

import random
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cached_property

from ccm.config import GrammarConfig
from ccm.grammar.lexicon import CONNECTEURS, OPERATEURS
from ccm.grammar.units import DATE, DUREE, Valeur, appliquer, unite_resultat, valeur_de
from ccm.schema import Exemple, MarqueNom, Relation

_CONTRAINTES = (Relation.MEME_UTILISATEUR, Relation.DIFFERENT_UTILISATEUR)
_ALNUM = re.compile(r"\w")


@dataclass(frozen=True)
class _Mention:
    pas: str  # « M:t.j »
    texte: str
    nom: int
    type: str


class Contexte:
    """Ce que le masque lit d'un exemple : marques, valeurs, arêtes, contraintes."""

    def __init__(
        self,
        mentions: list[_Mention],
        nombres: dict[int, list[tuple[str, Valeur]]],  # proposition → (« N:k.j », valeur)
        n_props: int,
        conflits: Iterable[tuple[int, int]],
        depend: Iterable[tuple[int, int]],  # (a, b) : a dépend de b
        contraintes: Iterable[tuple[int, int]],
        differents: Iterable[tuple[int, int]],
        negatives: Iterable[int],
        vocabulaire: Iterable[str] = (),
    ):
        self.mentions, self.nombres, self.n_props = mentions, nombres, n_props
        self.conflit: dict[int, set[int]] = defaultdict(set)
        for a, b in conflits:
            self.conflit[a].add(b)
            self.conflit[b].add(a)
        directes: dict[int, set[int]] = defaultdict(set)
        for a, b in depend:
            directes[a].add(b)
        self.deps: dict[int, frozenset[int]] = {}
        for k in range(n_props):
            vus, pile = {k}, [k]
            while pile:
                for b in directes[pile.pop()] - vus:
                    vus.add(b)
                    pile.append(b)
            self.deps[k] = frozenset(vus)
        self.contrainte: dict[int, set[int]] = defaultdict(set)
        for a, b in contraintes:
            self.contrainte[a].add(b)
            self.contrainte[b].add(a)
        diff = {frozenset(p) for p in differents}
        self.negatives = frozenset(negatives)
        self.vocabulaire = frozenset(vocabulaire)

        self.par_nom: dict[int, list[_Mention]] = defaultdict(list)
        self.noms_prop: dict[int, set[int]] = defaultdict(set)
        self.mentions_prop: dict[int, list[str]] = defaultdict(list)
        types = {}
        for m in mentions:
            self.par_nom[m.nom].append(m)
            types[m.nom] = m.type
            if m.texte.isdigit():
                self.noms_prop[int(m.texte)].add(m.nom)
                self.mentions_prop[int(m.texte)].append(m.pas)
        self.partenaires = {
            a: {b for b in types if b != a and types[b] == types[a] and {a, b} not in diff}
            for a in types
        }
        self.question = [m for m in mentions if m.texte == "q"]
        self.marquees = frozenset(set(self.mentions_prop) | {k for k, v in nombres.items() if v})

    @classmethod
    def depuis_exemple(
        cls,
        ex: Exemple,
        valeurs: dict[int, str],
        negation: Sequence[str],
        vocabulaire: Iterable[str] = (),
    ) -> "Contexte":
        """`valeurs` : valeur_id → valeur (table de la conversation) ; `negation` : motifs
        des marques de négation (`ingest.conflits.negation`)."""
        textes = {"q": ex.question}
        textes |= {f"h{i}": m for i, m in enumerate(reversed(ex.historique), 1)}
        textes |= {str(p.local): p for p in ex.propositions}
        mentions, nombres = [], defaultdict(list)
        for t, tm in textes.items():
            for j, m in enumerate(tm.marques):
                if isinstance(m, MarqueNom):
                    mentions.append(_Mention(f"M:{t}.{j}", t, m.nom, str(m.type)))
                elif t.isdigit():
                    nombres[int(t)].append((f"N:{t}.{j}", valeur_de(m.unite, valeurs[m.valeur_id])))
        motifs = [re.compile(m, re.IGNORECASE) for m in negation]
        rels = ex.relations_props
        return cls(
            mentions,
            dict(nombres),
            len(ex.propositions),
            [(a, b) for a, b, r in rels if r == Relation.CONFLIT],
            [(a, b) for a, b, r in rels if r == Relation.DEPEND_DE],
            [(a, b) for a, b, r in ex.relations_noms if r in _CONTRAINTES],
            [(a, b) for a, b, r in ex.relations_noms if r == Relation.DIFFERENT_UTILISATEUR],
            [p.local for p in ex.propositions if any(m.search(p.texte) for m in motifs)],
            vocabulaire,
        )

    @cached_property
    def same_possible(self) -> bool:
        return any(self.partenaires[m.nom] & set(self.par_nom) for m in self.mentions)

    @cached_property
    def note_possible(self) -> bool:
        return len({m.nom for m in self.question}) >= 2

    @cached_property
    def declaration_possible(self) -> bool:
        return any(self.contrainte[m.nom] & set(self.par_nom) for m in self.mentions)


# --- Pile d'un CALCUL ----------------------------------------------------------------
# Genre d'une valeur pour savoir si une pile peut encore se réduire : unité, précision,
# valeur non nulle connue (pour ÷), durée entière connue (pour DATE ± durée).


def _genre(v: Valeur) -> tuple:
    entier = v.unite == DUREE and v.valeur == v.valeur.to_integral_value()
    return (v.unite, v.precision, v.unite != DATE and v.valeur != 0, entier)


def _combiner(op: str, a: tuple, b: tuple) -> tuple | None:
    if op == "÷" and not b[2]:
        return None
    if a[0] == DATE and b[0] == DUREE and op in ("+", "−") and not b[3]:
        return None
    u = unite_resultat(op, Valeur(a[0], 0, a[1]), Valeur(b[0], 0, b[1]))
    if u is None:
        return None
    if u == DATE:
        return (DATE, a[1], False, False)
    non_nul = (op == "÷" and a[2]) or (op in ("×", "MIN", "MAX") and a[2] and b[2])
    entier = u == DUREE and (a[0] == DATE or (op in ("+", "−", "MIN", "MAX") and a[3] and b[3]))
    return (u, None, non_nul, entier)


def _reductible(pile: list[Valeur]) -> bool:
    """La pile peut-elle finir en une valeur par des opérateurs seuls ?"""
    genres = {_genre(pile[-1])}
    for v in reversed(pile[:-1]):
        g = _genre(v)
        genres = {r for s in genres for op in OPERATEURS if (r := _combiner(op, g, s))}
        if not genres:
            return False
    return True


class Automate:
    def __init__(self, ctx: Contexte, cfg: GrammarConfig, synthese: bool = False):
        self.ctx, self.cfg, self.synthese = ctx, cfg, synthese
        self.pas_max = cfg.pas_max_synthese if synthese else cfg.pas_max
        self.suite: list[str] = []
        self.etat = "DEBUT"
        self.citees: set[int] = set()
        self.fini = False
        self.synthese_faite = False
        self.phrases = 0
        self.bloc: dict | None = None

    # --- Outils ------------------------------------------------------------------------

    @property
    def reste(self) -> int:
        return self.pas_max - len(self.suite)

    def _tient(self, apres: int) -> bool:
        """Ce pas, puis `apres` pas au moins jusqu'à FIN."""
        return 1 + apres <= self.reste

    def _operandes(self) -> list[tuple[str, Valeur]]:
        """Nombres d'un CALCUL : propositions citées, ou sources de la phrase de synthèse."""
        props = self.bloc["sources"] if self.bloc["synthese"] else self.citees
        return [n for k in sorted(props) for n in self.ctx.nombres.get(k, ())]

    def _paire_calcul(self, props: Iterable[int]) -> bool:
        ns = [v for k in props for _, v in self.ctx.nombres.get(k, ())]
        return any(
            appliquer(op, a, b) for i, a in enumerate(ns) for j, b in enumerate(ns) if i != j
            for op in OPERATEURS
        )  # fmt: skip

    def _segments(self) -> dict[str, int]:
        """Débuts de segment possibles → longueur minimale du segment."""
        c = self.ctx
        out = {f"P:{k}": 1 for k in range(c.n_props) if k not in self.citees}
        if self._paire_calcul(self.citees):
            out["CALCUL"] = 5
        conflit = [n for n, ok in ((4, any(c.conflit.values())), (5, c.n_props >= 2),
                                   (6, c.declaration_possible)) if ok]  # fmt: skip
        if conflit:
            out["CONFLIT"] = min(conflit)
        if c.same_possible:
            out |= {"SAME": 4, "ASK_SAME": 3}
        if c.note_possible:
            out |= {"NOTE_SAME": 3, "NOTE_DIFF": 3}
        return out

    def _synthese_possible(self) -> bool:
        return any(self.ctx.deps[k] & self.ctx.marquees for k in self.citees)

    # --- Pas permis ----------------------------------------------------------------------

    def autorises(self) -> frozenset[str]:
        if self.fini:
            return frozenset()
        return frozenset(getattr(self, f"_aut_{self.etat}")())

    def _aut_DEBUT(self):
        out = {"ABSTENTION"} if self._tient(1) else set()
        return out | {s for s, n in self._segments().items() if self._tient(n)}

    def _aut_ABST(self):
        return {"FIN"}

    def _aut_SEG(self):
        out = {"FIN"}
        segs = self._segments()
        if segs and self._tient(1 + min(segs.values())):
            out |= set(CONNECTEURS)
        if self.synthese and not self.synthese_faite and self._synthese_possible():
            if self._tient(7):
                out.add("SYNTHESE")
        return out

    def _aut_CONN(self):
        return {s for s, n in self._segments().items() if self._tient(n)}

    def _aut_FIN_SYNTH(self):
        return {"FIN"}

    # SAME, ASK_SAME, NOTE_SAME, NOTE_DIFF
    def _aut_M1(self):
        c = self.ctx
        if self.bloc["genre"] in ("NOTE_SAME", "NOTE_DIFF"):
            noms = {m.nom for m in c.question}
            return {m.pas for m in c.question if len(noms - {m.nom}) >= 1}
        return {m.pas for m in c.mentions if c.partenaires[m.nom] & set(c.par_nom)}

    def _aut_M2(self):
        c, a = self.ctx, self.bloc["noms"][0]
        if self.bloc["genre"] in ("NOTE_SAME", "NOTE_DIFF"):
            return {m.pas for m in c.question if m.nom != a}
        return {m.pas for b in c.partenaires[a] for m in c.par_nom.get(b, ())}

    def _aut_PREUVE(self):
        noms = set(self.bloc["noms"])
        return {f"P:{k}" for k in range(self.ctx.n_props) if self.ctx.noms_prop[k] & noms} | {
            "SANS_PREUVE"}  # fmt: skip

    # CONFLIT
    def _aut_CF0(self):
        c, out = self.ctx, set()
        if self._tient(3):
            out |= {f"P:{k}" for k, v in c.conflit.items() if v}
        if c.n_props >= 2 and self._tient(4):
            out.add("SANS_PREUVE")
        if c.declaration_possible and self._tient(5):
            out.add("DECLARATION")
        return out

    def _aut_CFP(self):
        b = self.bloc["props"]
        out = {"FIN_CONFLIT"} if len(b) >= 2 else set()
        if len(b) < 2 or self._tient(2):
            out |= {f"P:{k}" for k in self.ctx.conflit[b[0]] if k not in b}
        return out

    def _aut_CFS(self):
        b = self.bloc["props"]
        out = {"FIN_CONFLIT"} if len(b) >= 2 else set()
        if len(b) < self.cfg.sans_preuve_max and (len(b) < 2 or self._tient(2)):
            out |= {f"P:{k}" for k in range(self.ctx.n_props) if k not in b}
        return out

    def _aut_CFD1(self):
        c = self.ctx
        return {m.pas for m in c.mentions if c.contrainte[m.nom] & set(c.par_nom)}

    def _aut_CFD2(self):
        c = self.ctx
        return {m.pas for b in c.contrainte[self.bloc["noms"][0]] for m in c.par_nom.get(b, ())}

    def _aut_CFDP(self):
        b = self.bloc["props"]
        out = {"FIN_CONFLIT"} if b else set()
        if not b or self._tient(2):
            out |= {f"P:{k}" for k in range(self.ctx.n_props) if k not in b}
        return out

    # CALCUL
    def _aut_CALC(self):
        b, pile = self.bloc, self.bloc["pile"]
        apres = 3 if b["synthese"] else 1
        out = set()
        if len(pile) == 1 and b["ops"] >= 1:
            out.add("FIN_CALCUL")
        ops = self._operandes()
        for pas, v in ops:  # un même nombre peut servir plusieurs fois
            if not pile:  # premier opérande : il faut un second opérande et un opérateur
                besoin = 2
                ok = any(appliquer(op, v, w) for _, w in ops for op in OPERATEURS)
            else:  # un opérateur par élément de la pile
                besoin = len(pile)
                ok = _reductible([*pile, v])
            if (
                ok
                and b["n"] + 1 + besoin <= self.cfg.calcul_pas
                and self._tient(besoin + 1 + apres)
            ):
                out.add(pas)
        if len(pile) >= 2:
            for op in OPERATEURS:
                r = appliquer(op, pile[-2], pile[-1])
                if r is None or not _reductible([*pile[:-2], r]):
                    continue
                n_apres = len(pile) - 1
                if b["n"] + 1 + (n_apres - 1) <= self.cfg.calcul_pas and self._tient(
                    n_apres - 1 + 1 + apres
                ):
                    out.add(op)
        return out

    # Synthèse
    def _aut_SY0(self):
        return {"SOURCES"}

    def _aut_SYS(self):
        c, src = self.ctx, self.bloc["sources"]
        marque = bool(self._ensemble(src) & c.marquees)
        out = {"DEBUT"} if marque else set()
        if len(src) < self.cfg.sources_max:
            for k in sorted(self.citees - set(src)):
                if self._ensemble([*src, k]) & c.marquees:
                    ok = not src or self._tient(5)
                else:  # une autre source marquée doit suivre
                    ok = len(src) + 1 < self.cfg.sources_max and self._tient(6) and any(
                        c.deps[x] & c.marquees for x in self.citees - set(src) - {k})  # fmt: skip
                if ok:
                    out.add(f"P:{k}")
        return out

    def _ensemble(self, src) -> set[int]:
        return set().union(*(self.ctx.deps[k] for k in src)) if src else set()

    def _aut_SYE(self):
        c, b = self.ctx, self.bloc
        ens = b["ensemble"]
        out = {"FIN_PHRASE"} if b["pointeur"] else set()
        if self._tient(3):
            out |= {p for k in ens for p in c.mentions_prop.get(k, ())}
            out |= {p for k in ens for p, _ in c.nombres.get(k, ())}
            if self._paire_calcul(ens) and self._tient(4 + 3):
                out.add("CALCUL")
        if b["mots"] < self.cfg.mots_phrase and self._tient(3 if b["pointeur"] else 4):
            negatif = bool(ens & c.negatives)
            neg = set(self.cfg.negations)
            for w in c.vocabulaire:
                if w in neg and not negatif:
                    continue
                out.add(f"W:{w}")
                if b["premier"]:
                    out.add(f"W:{w[:1].upper()}{w[1:]}")
        return out

    def _aut_SYF(self):
        out = {"FIN_SYNTHESE"}
        if self.phrases < self.cfg.phrases_max and self._tient(6):
            out.add("SOURCES")
        return out

    # --- Transitions -----------------------------------------------------------------------

    def avancer(self, pas: str) -> None:
        if pas not in self.autorises():
            raise ValueError(f"pas interdit à l'état {self.etat} : {pas!r}")
        self.suite.append(pas)
        getattr(self, f"_av_{self.etat}")(pas)

    def _debut_segment(self, pas: str) -> None:
        if pas.startswith("P:"):
            self.citees.add(int(pas[2:]))
            self.etat = "SEG"
        elif pas == "CALCUL":
            self._ouvrir_calcul()
        elif pas == "CONFLIT":
            self.bloc, self.etat = {"props": []}, "CF0"
        else:  # SAME, ASK_SAME, NOTE_SAME, NOTE_DIFF
            self.bloc, self.etat = {"genre": pas, "noms": []}, "M1"

    def _ouvrir_calcul(self, sources: set[int] | None = None) -> None:
        """`sources` : CALCUL d'une phrase de synthèse (opérandes pris dans ses sources)."""
        self.bloc = dict(pile=[], n=0, ops=0, synthese=sources is not None,
                         sources=sources, retour=self.etat, parent=self.bloc)  # fmt: skip
        self.etat = "CALC"

    def _av_DEBUT(self, pas):
        if pas == "ABSTENTION":
            self.etat = "ABST"
        else:
            self._debut_segment(pas)

    def _av_ABST(self, pas):
        self.fini = True

    def _av_SEG(self, pas):
        if pas == "FIN":
            self.fini = True
        elif pas == "SYNTHESE":
            self.synthese_faite, self.etat = True, "SY0"
        else:
            self.etat = "CONN"

    def _av_CONN(self, pas):
        self._debut_segment(pas)

    def _av_FIN_SYNTH(self, pas):
        self.fini = True

    def _av_M1(self, pas):
        self.bloc["noms"].append(self._nom(pas))
        self.etat = "M2"

    def _av_M2(self, pas):
        self.bloc["noms"].append(self._nom(pas))
        self.etat = "PREUVE" if self.bloc["genre"] == "SAME" else "SEG"

    def _av_PREUVE(self, pas):
        if pas.startswith("P:"):
            self.citees.add(int(pas[2:]))
        self.etat = "SEG"

    def _nom(self, pas: str) -> int:
        return next(m.nom for m in self.ctx.mentions if m.pas == pas)

    def _av_CF0(self, pas):
        if pas == "SANS_PREUVE":
            self.etat = "CFS"
        elif pas == "DECLARATION":
            self.bloc["noms"], self.etat = [], "CFD1"
        else:
            self.bloc["props"].append(int(pas[2:]))
            self.etat = "CFP"

    def _av_bloc_conflit(self, pas):
        if pas == "FIN_CONFLIT":
            self.citees |= set(self.bloc["props"])
            self.etat = "SEG"
        else:
            self.bloc["props"].append(int(pas[2:]))

    _av_CFP = _av_CFS = _av_CFDP = _av_bloc_conflit

    def _av_CFD1(self, pas):
        self.bloc["noms"].append(self._nom(pas))
        self.etat = "CFD2"

    def _av_CFD2(self, pas):
        self.etat = "CFDP"

    def _av_CALC(self, pas):
        b = self.bloc
        if pas == "FIN_CALCUL":
            self.bloc, self.etat = b["parent"], b["retour"]
            if b["synthese"]:
                self.bloc.update(pointeur=True, premier=False)
            else:
                self.etat = "SEG"
            return
        b["n"] += 1
        if pas in OPERATEURS:
            y, x = b["pile"].pop(), b["pile"].pop()
            b["pile"].append(appliquer(pas, x, y))
            b["ops"] += 1
        else:
            b["pile"].append(dict(self._operandes())[pas])

    def _av_SY0(self, pas):
        self.bloc, self.etat = {"sources": []}, "SYS"

    def _av_SYS(self, pas):
        if pas == "DEBUT":
            ens = self._ensemble(self.bloc["sources"])
            self.bloc = {"sources": self.bloc["sources"], "ensemble": ens, "mots": 0,
                         "pointeur": False, "premier": True}  # fmt: skip
            self.etat = "SYE"
        else:
            self.bloc["sources"].append(int(pas[2:]))

    def _av_SYE(self, pas):
        b = self.bloc
        if pas == "FIN_PHRASE":
            self.phrases += 1
            self.etat = "SYF"
        elif pas == "CALCUL":
            self._ouvrir_calcul(b["ensemble"])
        else:
            if pas.startswith("W:"):
                b["mots"] += bool(_ALNUM.match(pas[2:]))
            else:
                b["pointeur"] = True
            b["premier"] = False

    def _av_SYF(self, pas):
        if pas == "FIN_SYNTHESE":
            self.etat = "FIN_SYNTH"
        else:
            self.bloc, self.etat = {"sources": []}, "SYS"


def masques(
    ctx: Contexte, suite: Sequence[str], cfg: GrammarConfig, synthese: bool = False
) -> list[frozenset[str]]:
    """Pas permis avant chaque pas de `suite` (erreur si un pas est interdit)."""
    a, out = Automate(ctx, cfg, synthese), []
    for pas in suite:
        out.append(a.autorises())
        a.avancer(pas)
    return out


def accepter(ctx: Contexte, suite: Sequence[str], cfg: GrammarConfig, synthese=False) -> bool:
    a = Automate(ctx, cfg, synthese)
    try:
        for pas in suite:
            a.avancer(pas)
    except ValueError:
        return False
    return a.fini


def decoder_au_hasard(
    ctx: Contexte, cfg: GrammarConfig, graine: int | str, synthese: bool = False
) -> list[str]:
    """Un pas tiré au hasard dans le masque à chaque pas ; erreur en cas d'impasse."""
    rng, a = random.Random(graine), Automate(ctx, cfg, synthese)
    while not a.fini:
        permis = sorted(a.autorises())
        if not permis:
            raise RuntimeError(f"impasse après {a.suite}")
        a.avancer(rng.choice(permis))
    return a.suite
