"""Gabarits d'affichage (SPEC.md §11) et écriture des nombres.

Le texte affiché est une suite de fragments. Chaque fragment dit d'où il vient :
- « gabarit » : morceau d'une chaîne fixe de ce module ;
- « texte » : texte original du stock (proposition, ou surface d'un nombre) ;
- « nom » : surface d'une mention du contexte ou de la question ;
- « calcul » : résultat d'un calcul sur des nombres cités ;
- « ref » : pièce, page, rang ou numéro de citation, lus dans le stock ;
- « mot » : mot libre d'une synthèse (SPEC.md §10 bis) ;
- « erreur » : message d'erreur du vérificateur.
Le test T5 lit ces genres.
"""

import string
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction

from ccm.grammar.units import DATE, DUREE, POURCENT, SANS_UNITE

# --- Gabarits --------------------------------------------------------------------------

CONNECTEURS = {"ET": "et", "MAIS": "mais", "DONC": "donc", "EN_REVANCHE": "en revanche",
               "PAR_AILLEURS": "par ailleurs"}  # fmt: skip
INFERENCE = "{c} (inférence du modèle)"
ABSTENTION = "Les passages trouvés ne répondent pas à cette question."
CITATION = "[{n}] {texte} ({ref})"
CONTEXTE = "Contexte : {texte} ({ref})"
REF = "pièce {piece}, page {page}"
REF_OCR = "pièce {piece}, à vérifier sur la page {page}"
SOURCE_DATEE = "[{n}] {texte} ({ref} ; date : {date})"
SAME_PREUVE = "Hypothèse : « {a} » et « {b} » sont {meme}. Source [{n}] : « {texte} » ({ref})."
SAME_SANS = "Hypothèse fondée sur la seule ressemblance des noms : « {a} » et « {b} »."
NOTE_SAME = "Noté : « {a} » et « {b} » sont {meme} (votre déclaration)."
NOTE_DIFF = "Noté : « {a} » et « {b} » sont {diff} (votre déclaration)."
ASK_SAME = "« {a} » et « {b} » sont-ils {meme} ?"
CALCUL = "Calcul : {formule} = {resultat}"
OPERANDE = "{valeur} [{n}]"
CONFLIT = "Conflit entre sources."
CONFLIT_SANS_PREUVE = "Contradiction possible entre ces passages (lecture du modèle, à vérifier)."
DECLARATION = "Vous avez dit que « {a} » et « {b} » sont {meme}."
RANG = "Rang : {rangs}."
RANG_PIECE = "pièce {piece} : {rang}"
LIEN = "Lien non confirmé : « {y} » (cette citation) et « {x} ». Ressemblance : {relation}."
AUCUN_NOM = "Cette citation ne nomme aucune personne ni entité de la question."
AUTRES = "Autres passages pertinents :"
DOUBLONS = "Aussi dans : {lieux}."
DOUBLONS_UN_DE_PLUS = "Aussi dans : {lieux}, et {n} autre endroit."
DOUBLONS_PLUS = "Aussi dans : {lieux}, et {n} autres endroits."
SYNTHESE = "Synthèse du modèle :"
LIEN_SOURCE = " ※ ({ref})"
ERREUR = "Erreur : {raison}"
SEPARATEURS = (", ", " ", " ; ")

MEME = {"PER": "la même personne", "ORG": "la même organisation", "LIEU": "le même lieu"}
MEME_AUTRE = "la même chose"
DIFF = {"PER": "des personnes différentes", "ORG": "des organisations différentes",
        "LIEU": "des lieux différents"}  # fmt: skip
DIFF_AUTRE = "des choses différentes"
RESSEMBLANCES = {
    "MEME_FAMILLE": "même nom de famille",
    "INITIALES_DE": "initiales",
    "PROCHE": "orthographe proche",
    "INCOMPATIBLE": "même nom de famille, prénoms ou genres incompatibles",
    "SIGLE_DE": "sigle",
    "INCLUS_DANS": "nom inclus dans l'autre",
    "ALIAS_DECLARE": "alias déclaré dans une pièce",
}
OPERATEURS = {"+": " + ", "−": " − ", "×": " × ", "÷": " ÷ "}
FONCTIONS = {"MIN": "min", "MAX": "max"}
PARENTHESES = ("(", ")", ", ")

_GABARITS = (INFERENCE, ABSTENTION, CITATION, CONTEXTE, REF, REF_OCR, SOURCE_DATEE, SAME_PREUVE,
             SAME_SANS, NOTE_SAME, NOTE_DIFF, ASK_SAME, CALCUL, OPERANDE, CONFLIT,
             CONFLIT_SANS_PREUVE, DECLARATION, RANG, RANG_PIECE, LIEN, AUCUN_NOM, AUTRES,
             SYNTHESE, LIEN_SOURCE, ERREUR, DOUBLONS, DOUBLONS_UN_DE_PLUS,
             DOUBLONS_PLUS)  # fmt: skip


def _morceaux(modele: str) -> list[str]:
    return [lit for lit, _, _, _ in string.Formatter().parse(modele) if lit]


PIECES_FIXES: frozenset[str] = frozenset(
    [p for g in _GABARITS for p in _morceaux(g)]
    + [*CONNECTEURS.values(), *MEME.values(), MEME_AUTRE, *DIFF.values(), DIFF_AUTRE]
    + [*RESSEMBLANCES.values(), *OPERATEURS.values(), *FONCTIONS.values(), *PARENTHESES]
    + list(SEPARATEURS)
)


# --- Fragments ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frag:
    genre: str
    texte: str


@dataclass
class Bloc:
    style: str  # citation, contexte, connecteur, identite, note, calcul, conflit, ancrage,
    #             abstention, autres, synthese, doublons, erreur
    frags: list[Frag] = field(default_factory=list)

    @property
    def texte(self) -> str:
        return "".join(f.texte for f in self.frags)


Valeurs = Frag | list[Frag]


def gabarit(modele: str, **valeurs: Valeurs) -> list[Frag]:
    """Fragments d'un gabarit : ses morceaux fixes, et les valeurs à leur place."""
    out = []
    for lit, nom, _, _ in string.Formatter().parse(modele):
        if lit:
            out.append(Frag("gabarit", lit))
        if nom is not None:
            v = valeurs[nom]
            out += v if isinstance(v, list) else [v]
    return out


def fixe(texte: str) -> Frag:
    assert texte in PIECES_FIXES, texte
    return Frag("gabarit", texte)


def joindre(parties: list[list[Frag]], sep: str = ", ") -> list[Frag]:
    out = []
    for i, p in enumerate(parties):
        out += ([fixe(sep)] if i else []) + p
    return out


def meme(type_: str) -> Frag:
    return fixe(MEME.get(type_, MEME_AUTRE))


def diff(type_: str) -> Frag:
    return fixe(DIFF.get(type_, DIFF_AUTRE))


# --- Nombres ----------------------------------------------------------------------------

_PLURIELS = {"an": "ans", "jour": "jours", "heure": "heures", "minute": "minutes"}
HEURE_DU_JOUR = "heure du jour"


def _decimales_finies(x: Fraction) -> int | None:
    """Nombre de décimales de l'écriture finie de x, ou None si elle est infinie."""
    d, n2, n5 = x.denominator, 0, 0
    while d % 2 == 0:
        d, n2 = d // 2, n2 + 1
    while d % 5 == 0:
        d, n5 = d // 5, n5 + 1
    return max(n2, n5) if d == 1 else None


def ecrire_nombre(x: Fraction, decimales: int) -> str:
    """« 1 234,5 » ; « ≈ 0,33 » si l'écriture décimale exacte est infinie."""
    k = _decimales_finies(x)
    approche = k is None
    if approche:
        k, x = decimales, Fraction(round(x, decimales))
    signe, x = ("−" if x < 0 else ""), abs(x)
    entier = int(x)
    frac = x - entier
    chiffres = f"{entier:,}".replace(",", " ")
    if k:
        dec = str(int(frac * 10**k)).rjust(k, "0").rstrip("0")
        chiffres += f",{dec}" if dec else ""
    return ("≈ " if approche else "") + signe + chiffres


def ecrire_valeur(unite: str, v, precision: str | None, decimales: int) -> str:
    """Résultat d'un calcul avec son unité (algèbre des unités, SPEC.md §10)."""
    if unite == DATE:
        if isinstance(v, date):
            return v.strftime("%d/%m/%Y")
        return v if len(v) == 4 else f"{v[5:7]}/{v[:4]}"
    if unite == POURCENT:
        return f"{ecrire_nombre(v * 100, decimales)} %"
    n = ecrire_nombre(v, decimales)
    if unite == SANS_UNITE:
        return n
    if unite == HEURE_DU_JOUR and v.denominator == 1 and 0 <= v < 24 * 60:
        return f"{int(v) // 60} h {int(v) % 60:02d}"
    if unite == HEURE_DU_JOUR:
        unite = "minute"
    if unite == DUREE or unite in _PLURIELS:
        return f"{n} {_PLURIELS[unite] if abs(v) >= 2 else unite}"
    return f"{n} {unite}"
