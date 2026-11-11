"""Vérificateur (SPEC.md §11) : la suite de pas du modèle devient le texte affiché.

Code pur, sans modèle. Étapes :
1. Relecture : la suite repasse dans l'automate ; refusée → erreur affichée et tracée.
2. Dépendances : fermeture DEPEND_DE (toute la base) de chaque proposition citée,
   affichée avant elle, style « contexte ».
3. Calculs : chaque opérande vient d'une proposition citée (d'une source de la phrase,
   en synthèse) ; résultat en décimal exact (fractions) ; formule entière.
4. Conflits : arêtes CONFLIT de toute la base ; un autre côté non affiché ajoute un bloc
   CONFLIT (pièces ignorées par l'utilisateur exclues). CONFLIT SANS_PREUVE n'ajoute rien.
5. Ancrage : liens sûrs (même nom, contrainte MEME, SAME de la réponse) depuis la
   question ; sinon note « Lien non confirmé » (relations 2 à 11) ou « aucune personne ».
6. Passages non cités : probabilité de sélection ≥ seuil, 10 au plus, avec dépendances.
7. Rendu : texte original lu dans le stock par `prop_id`, pièce, page, OCR bas ; sous chaque
   passage, les endroits de ses copies (§5, étape 7), `doublons_max` au plus.
8. Contraintes : NOTE_SAME, NOTE_DIFF enregistrées, puis une seule relance.
9. Trace : ligne de la table `trace`.
"""

import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from fractions import Fraction

from ccm.anonymize.exemple import Message, zones_message, zones_propositions
from ccm.anonymize.names import norme
from ccm.config import GrammarConfig, IngestConfig, VerifyConfig
from ccm.grammar.automaton import Automate, Contexte
from ccm.grammar.lexicon import CONNECTEURS, OPERATEURS
from ccm.grammar.units import DATE, DUREE, Valeur, unite_resultat
from ccm.schema import RELATION_IDS, Exemple, GenreContrainte, Relation, TypeArete
from ccm.verify import render as R
from ccm.verify.render import Bloc, Frag, fixe, gabarit
from ccm.verify.trace import ecrire_reponse

RESSEMBLANCES = frozenset(r for r, ids in RELATION_IDS.items() if 2 <= ids[0] <= 11)


@dataclass(frozen=True)
class Entree:
    """Ce que le vérificateur lit en plus de la suite : l'exemple, la table des valeurs,
    les messages (pour les surfaces des mentions de la question et de l'historique)."""

    ex: Exemple
    valeurs: dict[int, str]  # valeur_id → valeur (table de la conversation)
    question: Message
    historique: tuple[Message, ...] = ()  # dans l'ordre de l'exemple, le plus récent en fin
    probabilites: dict[int, float] = field(default_factory=dict)  # local → sélection
    conv_id: str | None = None
    reponse_id: str | None = None  # ligne de trace écrite par la recherche


@dataclass
class Reponse:
    blocs: list[Bloc]
    citees: list[int]  # prop_id, dans l'ordre de citation
    erreur: str | None = None
    reponse_id: str | None = None
    contraintes: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def texte(self) -> str:
        return "\n".join(b.texte for b in self.blocs)


# --- Découpage d'une suite acceptée ------------------------------------------------------


def _props(pas: Sequence[str]) -> list[int]:
    return [int(p[2:]) for p in pas]


def _calcul(suite: Sequence[str], i: int) -> tuple[list[str], int]:
    j = suite.index("FIN_CALCUL", i)
    return list(suite[i + 1 : j]), j + 1


def decouper(suite: Sequence[str]) -> list[tuple]:
    """Segments d'une suite acceptée par l'automate."""
    out, i = [], 0
    while suite[i] != "FIN":
        pas = suite[i]
        if pas in CONNECTEURS or pas == "ABSTENTION":
            out.append((pas,))
            i += 1
        elif pas.startswith("P:"):
            out.append(("CITE", int(pas[2:])))
            i += 1
        elif pas == "CALCUL":
            corps, i = _calcul(suite, i)
            out.append(("CALCUL", corps))
        elif pas == "CONFLIT":
            j = suite.index("FIN_CONFLIT", i)
            corps, i = suite[i + 1 : j], j + 1
            if corps[0] == "SANS_PREUVE":
                out.append(("CONFLIT_SANS_PREUVE", _props(corps[1:])))
            elif corps[0] == "DECLARATION":
                out.append(("DECLARATION", corps[1], corps[2], _props(corps[3:])))
            else:
                out.append(("CONFLIT", _props(corps)))
        elif pas == "SAME":
            a, b, p = suite[i + 1 : i + 4]
            out.append(("SAME", a, b, None if p == "SANS_PREUVE" else int(p[2:])))
            i += 4
        elif pas in ("NOTE_SAME", "NOTE_DIFF", "ASK_SAME"):
            out.append((pas, suite[i + 1], suite[i + 2]))
            i += 3
        elif pas == "SYNTHESE":
            phrases, i = [], i + 1
            while suite[i] == "SOURCES":
                j = suite.index("DEBUT", i)
                sources, elements, i = _props(suite[i + 1 : j]), [], j + 1
                while suite[i] != "FIN_PHRASE":
                    if suite[i] == "CALCUL":
                        corps, i = _calcul(suite, i)
                        elements.append(("CALCUL", corps))
                    else:
                        elements.append(suite[i])
                        i += 1
                phrases.append((sources, elements))
                i += 1
            out.append(("SYNTHESE", phrases))
            i += 1  # FIN_SYNTHESE
        else:
            raise ValueError(f"pas inattendu : {pas!r}")
    return out


def citees_par_segment(seg: tuple) -> list[int]:
    """Propositions locales citées par un segment (CITE, preuve d'un SAME, blocs CONFLIT)."""
    if seg[0] == "CITE":
        return [seg[1]]
    if seg[0] == "SAME":
        return [] if seg[3] is None else [seg[3]]
    if seg[0] in ("CONFLIT", "CONFLIT_SANS_PREUVE"):
        return seg[1]
    if seg[0] == "DECLARATION":
        return seg[3]
    return []


# --- Calcul exact ------------------------------------------------------------------------


def exact(v: Valeur) -> Valeur:
    """Valeur du masque (Decimal) → valeur exacte (Fraction) ; les dates ne changent pas."""
    if v.unite == DATE:
        return v
    return Valeur(v.unite, Fraction(v.valeur), v.precision)


def appliquer_exact(op: str, a: Valeur, b: Valeur) -> Valeur | None:
    """« a op b » en arithmétique exacte, ou None (algèbre des unités, division par zéro)."""
    u = unite_resultat(op, a, b)
    if u is None:
        return None
    x, y = a.valeur, b.valeur
    if op in ("MIN", "MAX"):
        return (min if op == "MIN" else max)((a, b), key=lambda v: v.valeur)
    if a.unite == DATE and b.unite == DATE:
        return Valeur(DUREE, Fraction((x - y).days))
    if u == DATE:
        if y.denominator != 1:
            return None
        return Valeur(DATE, x + timedelta(int(y)) if op == "+" else x - timedelta(int(y)), "JOUR")
    if op == "+":
        return Valeur(u, x + y)
    if op == "−":
        return Valeur(u, x - y)
    if op == "×":
        return Valeur(u, x * y)
    return None if y == 0 else Valeur(u, x / y)


_PRIORITE = {"+": 1, "−": 1, "×": 2, "÷": 2}
_IDENTITE = {"NOTE_SAME": R.NOTE_SAME, "NOTE_DIFF": R.NOTE_DIFF, "ASK_SAME": R.ASK_SAME}


# --- Vérificateur ------------------------------------------------------------------------


class _Verif:
    def __init__(self, con, entree: Entree, cfg: IngestConfig, vcfg: VerifyConfig, ctx: Contexte):
        self.con, self.e, self.cfg, self.vcfg, self.ctx = con, entree, cfg, vcfg, ctx
        ex = entree.ex
        self.prop_id = [p.prop_id for p in ex.propositions]
        self.local = {p: k for k, p in enumerate(self.prop_id)}
        # Surfaces des marques : « M:t.j » / « N:t.j » → (texte, début, fin).
        self.surfaces: dict[str, str] = {}
        textes = {"q": (entree.question.texte, zones_message(entree.question, cfg))}
        for i, m in enumerate(reversed(entree.historique), 1):
            textes[f"h{i}"] = (m.texte, zones_message(m, cfg))
        for p, (t, zs) in zones_propositions(con, self.prop_id, cfg).items():
            textes[str(self.local[p])] = (t, zs)
        for t, (texte, zs) in textes.items():
            for j, z in enumerate(zs):
                s = texte[z.debut : z.fin]
                self.surfaces[f"M:{t}.{j}"] = self.surfaces[f"N:{t}.{j}"] = s
        self.mentions = {m.pas: m for m in ctx.mentions}
        self.ignorees = {
            pc
            for (pc,) in con.execute(
                "SELECT piece_id FROM contrainte WHERE conv_id = ? AND genre = ?",
                (entree.conv_id, str(GenreContrainte.IGNORER_SOURCE)),
            )
        }
        self.numeros: dict[int, int] = {}  # prop_id → numéro affiché
        self.affichees: set[int] = set()  # prop_id déjà affichés (citations, contexte, conflits)
        self.copies_vues: set[int] = set()  # passages dont les copies sont déjà listées
        self.blocs: list[Bloc] = []
        self.contraintes: list[tuple[str, str, str]] = []

    # --- Stock (étape 7) ---------------------------------------------------------------

    def _ligne(self, p: int) -> tuple[str, str, int, float | None, int]:
        return self.con.execute(
            "SELECT p.texte, p.piece_id, p.page, p.ocr_conf, c.rang FROM proposition p "
            "JOIN piece c USING (piece_id) WHERE p.prop_id = ?",
            (p,),
        ).fetchone()

    def _ref(self, p: int) -> list[Frag]:
        _, piece, page, conf, _ = self._ligne(p)
        modele = R.REF_OCR if conf is not None and conf < self.cfg.anonymiseur.ocr_bas else R.REF
        return gabarit(modele, piece=Frag("ref", piece), page=Frag("ref", str(page)))

    def _numero(self, p: int) -> Frag:
        n = self.numeros.setdefault(p, len(self.numeros) + 1)
        return Frag("ref", str(n))

    def _texte(self, p: int) -> Frag:
        return Frag("texte", self._ligne(p)[0])

    def _doublons(self, p: int) -> list[Bloc]:
        """« Aussi dans : … » : copies du passage (même groupe de doublons), une fois par
        réponse ; au-delà de `doublons_max` endroits, seulement leur nombre."""
        if p in self.copies_vues:
            return []
        self.copies_vues.add(p)
        lieux = list(dict.fromkeys(self.con.execute(
            "SELECT piece_id, page FROM proposition WHERE groupe_doublon = (SELECT groupe_doublon "
            "FROM proposition WHERE prop_id = ?) AND prop_id != ? ORDER BY piece_id, page",
            (p, p),
        )))  # fmt: skip
        if not lieux:
            return []
        montres, reste = lieux[: self.vcfg.doublons_max], len(lieux) - self.vcfg.doublons_max
        parties = [gabarit(R.REF, piece=Frag("ref", pc), page=Frag("ref", str(pg)))
                   for pc, pg in montres]  # fmt: skip
        modele = (
            R.DOUBLONS if reste <= 0 else R.DOUBLONS_UN_DE_PLUS if reste == 1 else R.DOUBLONS_PLUS
        )
        f = gabarit(modele, lieux=R.joindre(parties, " ; "), n=Frag("ref", str(reste)))
        return [Bloc("doublons", f)]

    def _bloc(self, style: str, frags: list[Frag], p: int) -> list[Bloc]:
        """Un passage affiché, suivi des endroits de ses copies."""
        return [Bloc(style, frags), *self._doublons(p)]

    def _citation(self, p: int) -> list[Frag]:
        self.affichees.add(p)
        return gabarit(R.CITATION, n=self._numero(p), texte=self._texte(p), ref=self._ref(p))

    def _source(self, p: int) -> list[Frag]:
        """Source d'un bloc CONFLIT : extrait, pièce et date (dates lues dans la phrase)."""
        self.affichees.add(p)
        dates = [Frag("texte", s) for (s,) in self.con.execute(
            "SELECT surface FROM nombre WHERE prop_id = ? AND genre = 'DATE' ORDER BY debut", (p,)
        )]  # fmt: skip
        if not dates:
            return self._citation(p)
        return gabarit(R.SOURCE_DATEE, n=self._numero(p), texte=self._texte(p), ref=self._ref(p),
                       date=R.joindre([[d] for d in dates]))  # fmt: skip

    def _rangs(self, props: list[int]) -> list[Bloc]:
        lignes = [(self._ligne(p)[1], self._ligne(p)[4]) for p in props]
        rangs = dict(lignes)
        if any(r == 0 for r in rangs.values()) or len(set(rangs.values())) < 2:
            return []
        parties = [gabarit(R.RANG_PIECE, piece=Frag("ref", pc), rang=Frag("ref", str(r)))
                   for pc, r in rangs.items()]  # fmt: skip
        return [Bloc("conflit", gabarit(R.RANG, rangs=R.joindre(parties)))]

    # --- Étape 2 : dépendances -------------------------------------------------------------

    def fermeture(self, p: int) -> list[int]:
        vus, pile = {p}, [p]
        while pile:
            for (d,) in self.con.execute(
                "SELECT dst FROM arete WHERE src = ? AND type = ?",
                (pile.pop(), str(TypeArete.DEPEND_DE)),
            ):
                if d not in vus:
                    vus.add(d)
                    pile.append(d)
        return sorted(vus - {p})

    def _dependances(self, props: list[int]) -> list[Bloc]:
        out = []
        for d in sorted({d for p in props for d in self.fermeture(p)} - set(props)):
            if d in self.affichees:
                continue
            self.affichees.add(d)
            f = gabarit(R.CONTEXTE, texte=self._texte(d), ref=self._ref(d))
            out.append(Bloc("contexte", f))
        return out

    # --- Étape 4 : conflits de toute la base -----------------------------------------------

    def _piece(self, p: int) -> str:
        return self._ligne(p)[1]

    def conflits_base(self, p: int) -> list[int]:
        return sorted(
            d
            for (d,) in self.con.execute(
                "SELECT dst FROM arete WHERE src = ? AND type = ?", (p, str(TypeArete.CONFLIT))
            )
            if self._piece(d) not in self.ignorees
        )

    def _conflits_ajoutes(self, props: list[int], citees_reponse: set[int]) -> list[Bloc]:
        out = []
        for p in props:
            autres = [d for d in self.conflits_base(p)
                      if d not in self.affichees and d not in citees_reponse]  # fmt: skip
            if not autres:
                continue
            out.append(Bloc("conflit", [fixe(R.CONFLIT)]))
            out += [b for x in [p, *autres] for b in self._bloc("conflit", self._source(x), x)]
            out += self._rangs([p, *autres])
        return out

    # --- Étape 3 : calculs --------------------------------------------------------------

    def calcul(self, corps: list[str], permises: set[int], formule: bool = True) -> list[Frag]:
        nombres = {pas: v for vs in self.ctx.nombres.values() for pas, v in vs}
        pile: list[tuple[Valeur, list[Frag], int]] = []
        for pas in corps:
            if pas in OPERATEURS:
                (b, fb, pb), (a, fa, pa) = pile.pop(), pile.pop()
                r = appliquer_exact(pas, a, b)
                if r is None:
                    raise ValueError(f"calcul impossible : {pas}")
                if pas in R.FONCTIONS:
                    f = [fixe(R.FONCTIONS[pas]), fixe("("), *fa, fixe(", "), *fb, fixe(")")]
                    pile.append((r, f, 3))
                    continue
                q = _PRIORITE[pas]
                fa = fa if pa >= q else [fixe("("), *fa, fixe(")")]
                fb = fb if pb > q or (pb == q and pas in "+×") else [fixe("("), *fb, fixe(")")]
                pile.append((r, [*fa, fixe(R.OPERATEURS[pas]), *fb], q))
            else:
                k = int(pas[2:].split(".")[0])
                if k not in permises:
                    raise ValueError(f"opérande hors des propositions citées : {pas}")
                v = Frag("texte", self.surfaces[pas])
                p = self.prop_id[k]
                f = gabarit(R.OPERANDE, valeur=v, n=self._numero(p)) if p in self.numeros else [v]
                pile.append((exact(nombres[pas]), f, 3))
        (r, f, _), = pile  # fmt: skip
        res = Frag("calcul", R.ecrire_valeur(r.unite, r.valeur, r.precision, self.vcfg.decimales))
        return gabarit(R.CALCUL, formule=f, resultat=res) if formule else [res]

    # --- Étape 5 : ancrage -----------------------------------------------------------------

    def ancrage(self, segments: list[tuple]) -> dict[int, list[Frag]]:
        """Notes d'ancrage par proposition locale citée."""
        c, ex = self.ctx, self.e.ex
        racine = {m.nom for m in c.question}
        for i in range(1, len(ex.historique) + 1):
            if racine:
                break
            racine = {m.nom for m in c.mentions if m.texte == f"h{i}"}
        if not racine:
            return {}
        # Liens sûrs : classes de noms (même nom, MEME de l'utilisateur, SAME de la réponse).
        parent: dict[int, int] = {}

        def classe(n: int) -> int:
            while parent.get(n, n) != n:
                n = parent[n]
            return n

        paires = [(a, b) for a, b, r in ex.relations_noms if r == Relation.MEME_UTILISATEUR]
        paires += [(self.mentions[s[1]].nom, self.mentions[s[2]].nom)
                   for s in segments if s[0] == "SAME"]  # fmt: skip
        for a, b in paires:
            parent[classe(a)] = classe(b)
        ressemble = defaultdict(list)
        for a, b, r in ex.relations_noms:
            if r in RESSEMBLANCES:
                ressemble[a].append((b, r))
                ressemble[b].append((a, r))

        ordre = list(dict.fromkeys(k for s in segments for k in citees_par_segment(s)))
        noms_ancres, classes = set(racine), {classe(n) for n in racine}
        ancrees, notes = set(), {}
        while True:
            neuve = next((k for k in ordre if k not in ancrees
                          and {classe(n) for n in c.noms_prop[k]} & classes), None)  # fmt: skip
            if neuve is None:
                for k in ordre:
                    if k in ancrees:
                        continue
                    lien = next(((y, x, r) for y in sorted(c.noms_prop[k])
                                 for x, r in ressemble[y] if x in noms_ancres), None)  # fmt: skip
                    if lien:
                        notes[k] = self._note_lien(k, *lien)
                        neuve = k
                        break
            if neuve is None:
                break
            ancrees.add(neuve)
            noms_ancres |= c.noms_prop[neuve]
            classes |= {classe(n) for n in c.noms_prop[neuve]}
        for k in ordre:
            if k not in ancrees and c.noms_prop[k]:
                notes[k] = [fixe(R.AUCUN_NOM)]
        return notes

    def _surface_nom(self, nom: int, textes: Sequence[str]) -> Frag:
        for t in textes:
            for m in self.ctx.mentions:
                if m.nom == nom and m.texte == t:
                    return Frag("nom", self.surfaces[m.pas])
        m = next(m for m in self.ctx.mentions if m.nom == nom)
        return Frag("nom", self.surfaces[m.pas])

    def _note_lien(self, k: int, y: int, x: int, r: Relation) -> list[Frag]:
        textes = ["q", *(f"h{i}" for i in range(1, len(self.e.ex.historique) + 1))]
        return gabarit(R.LIEN, y=self._surface_nom(y, [str(k)]), x=self._surface_nom(x, textes),
                       relation=fixe(R.RESSEMBLANCES[str(r)]))  # fmt: skip

    # --- Identité --------------------------------------------------------------------------

    def _nom(self, pas: str) -> Frag:
        return Frag("nom", self.surfaces[pas])

    def _type(self, pas: str) -> str:
        return self.mentions[pas].type

    def _noter(self, genre: str, a: str, b: str) -> None:
        """Étape 8 : contrainte de l'utilisateur (NOTE_SAME → MEME, NOTE_DIFF → DIFFERENT)."""
        g = GenreContrainte.MEME if genre == "NOTE_SAME" else GenreContrainte.DIFFERENT
        na, nb = (norme(self.surfaces[x], self.cfg.noms) for x in (a, b))
        self.con.execute(
            "INSERT INTO contrainte (conv_id, genre, a_norme, b_norme, piece_id, auteur, date) "
            "VALUES (?, ?, ?, ?, NULL, 'utilisateur', ?)",
            (self.e.conv_id, str(g), na, nb, datetime.now().isoformat(timespec="seconds")),
        )
        self.contraintes.append((str(g), na, nb))

    # --- Étape 6 : passages non cités -----------------------------------------------------

    def autres_passages(self, citees: set[int]) -> list[Bloc]:
        cands = sorted(
            ((-pr, k) for k, pr in self.e.probabilites.items()
             if pr >= self.vcfg.seuil_selection and self.prop_id[k] not in citees),
        )[: self.vcfg.passages_max]  # fmt: skip
        if not cands:
            return []
        out = [Bloc("autres", [fixe(R.AUTRES)])]
        for _, k in cands:
            p = self.prop_id[k]
            out += self._dependances([p])
            out += self._bloc("autres", self._citation(p), p)
        return out

    # --- Rendu des segments ---------------------------------------------------------------

    def rendre(self, segments: list[tuple]) -> None:
        notes = self.ancrage(segments)
        citees_reponse = {self.prop_id[k] for s in segments for k in citees_par_segment(s)}
        permises: set[int] = set()
        for s in segments:
            g = s[0]
            locales = citees_par_segment(s)
            props = [self.prop_id[k] for k in locales]
            self.blocs += self._dependances(props)
            if g in CONNECTEURS:
                mot = fixe(R.CONNECTEURS[g])
                f = gabarit(R.INFERENCE, c=mot) if g == "DONC" else [mot]
                self.blocs.append(Bloc("connecteur", f))
            elif g == "ABSTENTION":
                self.blocs.append(Bloc("abstention", [fixe(R.ABSTENTION)]))
            elif g == "CITE":
                self.blocs += self._bloc("citation", self._citation(props[0]), props[0])
            elif g == "SAME":
                a, b = self._nom(s[1]), self._nom(s[2])
                if s[3] is None:
                    f = gabarit(R.SAME_SANS, a=a, b=b)
                else:
                    p = props[0]
                    self.affichees.add(p)
                    f = gabarit(R.SAME_PREUVE, a=a, b=b, meme=R.meme(self._type(s[1])),
                                n=self._numero(p), texte=self._texte(p),
                                ref=self._ref(p))  # fmt: skip
                blocs = self._bloc("identite", f, props[0]) if props else [Bloc("identite", f)]
                self.blocs += blocs
            elif g in ("NOTE_SAME", "NOTE_DIFF", "ASK_SAME"):
                t = self._type(s[1])
                f = gabarit(_IDENTITE[g], a=self._nom(s[1]), b=self._nom(s[2]), meme=R.meme(t),
                            diff=R.diff(t))  # fmt: skip
                if g != "ASK_SAME":
                    self._noter(g, s[1], s[2])
                self.blocs.append(Bloc("note" if g != "ASK_SAME" else "identite", f))
            elif g in ("CONFLIT", "CONFLIT_SANS_PREUVE"):
                tete = R.CONFLIT if g == "CONFLIT" else R.CONFLIT_SANS_PREUVE
                self.blocs.append(Bloc("conflit", [fixe(tete)]))
                self.blocs += [b for p in props for b in self._bloc("conflit", self._source(p), p)]
                self.blocs += self._rangs(props)
            elif g == "DECLARATION":
                f = gabarit(R.DECLARATION, a=self._nom(s[1]), b=self._nom(s[2]),
                            meme=R.meme(self._type(s[1])))  # fmt: skip
                self.blocs.append(Bloc("conflit", f))
                self.blocs += [
                    b for p in props for b in self._bloc("conflit", self._citation(p), p)
                ]
            elif g == "CALCUL":
                self.blocs.append(Bloc("calcul", self.calcul(s[1], permises)))
            elif g == "SYNTHESE":
                self._synthese(s[1])
            permises |= set(locales)
            for k in locales:
                if k in notes:
                    self.blocs.append(Bloc("ancrage", notes[k]))
            self.blocs += self._conflits_ajoutes(props, citees_reponse)
        self.blocs += self.autres_passages(citees_reponse)

    def _synthese(self, phrases) -> None:
        """Synthèse raisonnée (SPEC.md §10 bis, « Rendu ») : pointeurs remplacés par les
        surfaces du contexte ; un lien ※ par source."""
        self.blocs.append(Bloc("synthese", [fixe(R.SYNTHESE)]))
        for sources, elements in phrases:
            ens = set().union(*(self.ctx.deps[k] for k in sources))
            f: list[Frag] = []
            for el in elements:
                if isinstance(el, tuple):
                    morceau = self.calcul(el[1], ens, formule=False)
                elif el.startswith("W:"):
                    morceau = [Frag("mot", el[2:])]
                else:
                    morceau = [Frag("nom" if el.startswith("M:") else "texte", self.surfaces[el])]
                if f and not _colle(f[-1].texte, morceau[0].texte):
                    f.append(fixe(" "))
                f += morceau
            for k in sources:
                f += gabarit(R.LIEN_SOURCE, ref=self._ref(self.prop_id[k]))
            self.blocs.append(Bloc("synthese", f))


def _colle(avant: str, apres: str) -> bool:
    return apres[:1] in ".,)…" or avant[-1:] in "'’("


def verifier(
    con: sqlite3.Connection,
    entree: Entree,
    suite: Sequence[str],
    cfg: IngestConfig,
    gcfg: GrammarConfig,
    vcfg: VerifyConfig,
    *,
    synthese: bool = False,
    vocabulaire: frozenset[str] = frozenset(),
    modele: str = "",
    relancer: Callable[[], "Reponse"] | None = None,
) -> Reponse:
    """Texte affiché de la suite `suite` (SPEC.md §11, étapes 1 à 9). `relancer` : refait
    la recherche et la réponse après une contrainte notée (étape 8), une seule fois."""
    ex = entree.ex
    ctx = Contexte.depuis_exemple(ex, entree.valeurs, cfg.conflits.negation, vocabulaire)
    v = _Verif(con, entree, cfg, vcfg, ctx)

    # Étape 1 : relecture.
    a, erreur = Automate(ctx, gcfg, synthese), None
    try:
        for pas in suite:
            a.avancer(pas)
        if not a.fini:
            erreur = "suite non finie"
    except ValueError as e:
        erreur = f"pas {len(a.suite)} refusé : {e}"
    if erreur is None:
        try:
            v.rendre(decouper(suite))
        except (ValueError, KeyError) as e:
            erreur = f"vérification : {e}"
    if erreur is not None:
        v.blocs = [Bloc("erreur", gabarit(R.ERREUR, raison=Frag("erreur", erreur)))]

    # Étape 9 : trace.
    citees = list(dict.fromkeys(
        v.prop_id[k] for s in (decouper(suite) if erreur is None else [])
        for k in citees_par_segment(s)
    ))  # fmt: skip
    actions = {"suite": list(suite), "citees": citees, "erreur": erreur,
               "contraintes": v.contraintes}  # fmt: skip
    rid = ecrire_reponse(con, actions, reponse_id=entree.reponse_id, conv_id=entree.conv_id,
                         question=entree.question.texte, prop_ids=v.prop_id,
                         modele=modele)  # fmt: skip
    rep = Reponse(v.blocs, citees, erreur, rid, v.contraintes)

    # Étape 8 : une relance après une contrainte notée.
    if v.contraintes and relancer is not None:
        nouvelle = relancer()
        nouvelle.blocs[:0] = [b for b in rep.blocs if b.style == "note"]
        nouvelle.contraintes = v.contraintes + nouvelle.contraintes
        return nouvelle
    return rep
