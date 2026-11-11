"""Algèbre des unités (SPEC.md §10) : ce qu'un CALCUL peut faire de deux nombres cités.

Une valeur porte son unité : « € », « km »…, « % » (valeur déjà divisée par 100), « »
(rapport sans unité, et nombre écrit sans unité), « date » (date ISO ; `precision`), « jour »
(durée). Une date ne se calcule qu'à la précision JOUR. Le résultat est exact (décimal).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

POURCENT, SANS_UNITE, DATE, DUREE = "%", "", "date", "jour"
_FACTEURS = (POURCENT, SANS_UNITE)


@dataclass(frozen=True)
class Valeur:
    unite: str
    valeur: Decimal | date | str  # str : date à la précision MOIS ou ANNEE
    precision: str | None = None


def valeur_de(unite: str, cle: str) -> Valeur:
    """Valeur d'un nombre du stock (clé de `anonymize.units.cle_valeur`)."""
    if unite == DATE:
        if len(cle) == 10:
            return Valeur(DATE, date.fromisoformat(cle), "JOUR")
        return Valeur(DATE, cle, "MOIS" if len(cle) == 7 else "ANNEE")
    v = Decimal(cle)
    return Valeur(unite, v / 100 if unite == POURCENT else v)


def unite_resultat(op: str, a: Valeur, b: Valeur) -> str | None:
    """Unité du résultat de « a op b », ou None si l'algèbre l'interdit (sans les valeurs)."""
    ua, ub = a.unite, b.unite
    if DATE in (ua, ub):
        if op in ("MIN", "MAX") and ua == ub and a.precision == b.precision:
            return DATE
        if a.precision != "JOUR" or (ub == DATE and b.precision != "JOUR"):
            return None
        if op == "−" and ub == DATE:
            return DUREE
        return DATE if op in ("+", "−") and ub == DUREE else None
    if op in ("+", "−", "MIN", "MAX"):
        return ua if ua == ub else None
    if op == "×":
        return ua if ub in _FACTEURS else ub if ua in _FACTEURS else None
    if op == "÷":
        return SANS_UNITE if ua == ub else ua if ub in _FACTEURS else None
    return None


def appliquer(op: str, a: Valeur, b: Valeur) -> Valeur | None:
    """« a op b » en décimal exact, ou None (algèbre des unités, division par zéro)."""
    u = unite_resultat(op, a, b)
    if u is None:
        return None
    x, y = a.valeur, b.valeur
    if op in ("MIN", "MAX"):
        return (min if op == "MIN" else max)((a, b), key=lambda v: v.valeur)
    if u == DUREE and a.unite == DATE:
        return Valeur(DUREE, Decimal((x - y).days))
    if u == DATE:
        if y != y.to_integral_value():
            return None
        jours = timedelta(days=int(y))
        return Valeur(DATE, x + jours if op == "+" else x - jours, "JOUR")
    if op == "+":
        return Valeur(u, x + y)
    if op == "−":
        return Valeur(u, x - y)
    if op == "×":
        return Valeur(u, x * y)
    return None if y == 0 else Valeur(u, x / y)
