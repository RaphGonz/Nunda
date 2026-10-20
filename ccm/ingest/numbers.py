"""Étape 6 de l'ingestion : nombres et dates (SPEC.md §5).

Expressions régulières pour les formats français, essayées dans cet ordre ; une position
prise par un motif ne sert plus aux suivants :

0. zones exclues (les noms de l'étape 5, dont les adresses « 77 rue … ») ;
1. références (articles, numéros de PV, téléphones, IBAN, plaques) : jamais des nombres ;
2. dates « 7 décembre 2024 », « 1er décembre 2024 », « décembre 2024 », « 27/06/2025 » ;
3. heures du jour « 21h59 », « 5 h 03 », « 21:59 », « 21 h », « à 21 heures » ;
4. nombre en chiffres suivi d'une unité connue ;
5. nombre en lettres suivi d'une unité connue (seul cas où un nombre en lettres compte) ;
6. année seule (`annee_min` à `annee_max`) : date de précision ANNEE ;
7. nombre en chiffres sans unité (unité vide).

Valeurs : décimal exact (`decimal`) en texte ; date ISO (« 2024-12-07 », « 2024-12 »,
« 2024 ») ; heure du jour en minutes depuis minuit.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ccm.config import NombresConfig
from ccm.schema import GenreNombre, PrecisionDate

_SEP = "[   .]"  # séparateur de milliers
_CHIFFRES = rf"[-−+]?(?:\d{{1,3}}(?:{_SEP}\d{{3}})+|\d+)(?:,\d+)?"
_AVANT = r"(?<![\w,./])"


@dataclass(frozen=True)
class NombreLu:
    debut: int
    fin: int
    surface: str
    genre: GenreNombre
    valeur: str
    unite: str
    precision: PrecisionDate | None = None


def _decimal(surface: str) -> str:
    s = re.sub(_SEP, "", surface).replace(",", ".").replace("−", "-").lstrip("+")
    return str(Decimal(s))


def _lettres(mots: str, table: dict[str, int]) -> int:
    total = courant = 0
    for m in re.split(r"[\s-]+", mots.lower()):
        v = table.get(m)
        if v is None:  # « et »
            continue
        if v >= 1000:
            total += (courant or 1) * v
            courant = 0
        elif v >= 100:
            courant = (courant or 1) * v
        elif v == 20 and courant % 100 == 4:  # quatre-vingt
            courant += 76
        else:
            courant += v
    return total + courant


class _Detecteur:
    def __init__(self, cfg: NombresConfig):
        self.cfg = cfg
        self.references = [re.compile(rf"(?<!\w){r}(?!\w)") for r in cfg.references]
        mois = "|".join(cfg.mois)
        self.date_mois = re.compile(
            rf"(?<!\w)(?:(\d{{1,2}})(?:er)?\s+)?((?i:{mois}))\s+(\d{{4}})(?!\w)"
        )
        self.date_chiffres = re.compile(
            rf"{_AVANT}(\d{{1,2}})([/.-])(\d{{1,2}})\2(\d{{4}})(?![\w/])"
        )
        avant = "|".join(re.escape(a) for a in cfg.avant_heure_du_jour)
        self.heures = [
            re.compile(rf"{_AVANT}(?P<s>(?P<h>\d{{1,2}})\s?[hH:]\s?(?P<m>\d{{2}}))(?!\w)"),
            re.compile(rf"{_AVANT}(?P<s>(?P<h>\d{{1,2}})\s?h)(?!\w)"),
            re.compile(
                rf"(?<!\w)(?:{avant})\s+(?P<s>(?P<h>\d{{1,2}})\s+heures?(?:\s+(?P<m>\d{{2}}))?)(?!\w)"
            ),
        ]
        formes = [(u.unite, f) for u in cfg.unites for f in u.formes]
        self.unite_de = [(u, re.compile(f, re.IGNORECASE)) for u, f in formes]
        unites = "|".join(f"(?:{f})" for _, f in formes)
        self.avec_unite = re.compile(rf"{_AVANT}({_CHIFFRES})\s?((?:{unites})(?!\w))")
        mots = "|".join(sorted(cfg.lettres, key=len, reverse=True))
        self.en_lettres = re.compile(
            rf"(?<!\w)((?:{mots})(?:[\s-]+(?:et[\s-]+)?(?:{mots}))*)\s+((?:{unites})(?!\w))",
            re.IGNORECASE,
        )
        self.annee = re.compile(rf"{_AVANT}(\d{{4}})(?![\w/]|,\d)")
        self.sans_unite = re.compile(rf"{_AVANT}{_CHIFFRES}(?![\w/]|,\d)")

    def unite(self, surface: str) -> str:
        for u, r in self.unite_de:
            if r.fullmatch(surface):
                return u
        raise ValueError(surface)

    def __call__(self, texte: str, exclus: list[tuple[int, int]]) -> list[NombreLu]:
        pris = list(exclus)
        out: list[NombreLu] = []

        def libre(d: int, f: int) -> bool:
            return all(f <= a or d >= b for a, b in pris)

        def garder(d, f, genre, valeur, unite, precision=None):
            pris.append((d, f))
            out.append(NombreLu(d, f, texte[d:f], genre, valeur, unite, precision))

        for r in self.references:
            for m in r.finditer(texte):
                if libre(*m.span()):
                    pris.append(m.span())
        for m in self.date_mois.finditer(texte):
            jour, mois, an = m[1], self.cfg.mois.index(m[2].lower()) + 1, int(m[3])
            if libre(*m.span()) and _date(an, mois, int(jour or 1)):
                if jour:
                    garder(
                        *m.span(),
                        GenreNombre.DATE,
                        f"{an:04d}-{mois:02d}-{int(jour):02d}",
                        "date",
                        PrecisionDate.JOUR,
                    )
                else:
                    garder(
                        *m.span(),
                        GenreNombre.DATE,
                        f"{an:04d}-{mois:02d}",
                        "date",
                        PrecisionDate.MOIS,
                    )
        for m in self.date_chiffres.finditer(texte):
            j, mo, an = int(m[1]), int(m[3]), int(m[4])
            if libre(*m.span()) and _date(an, mo, j):
                garder(
                    *m.span(),
                    GenreNombre.DATE,
                    f"{an:04d}-{mo:02d}-{j:02d}",
                    "date",
                    PrecisionDate.JOUR,
                )
        hdj = self.cfg.unite_heure_du_jour
        for r in self.heures:  # la surface (groupe s) omet « à », « vers »
            for m in r.finditer(texte):
                h, mi = int(m["h"]), int(m.groupdict().get("m") or 0)
                if libre(*m.span("s")) and h <= 23 and mi <= 59:
                    garder(*m.span("s"), GenreNombre.NUM, str(h * 60 + mi), hdj)
        for m in self.avec_unite.finditer(texte):
            if libre(*m.span()):
                garder(*m.span(), GenreNombre.NUM, _decimal(m[1]), self.unite(m[2]))
        for m in self.en_lettres.finditer(texte):
            if libre(*m.span()):
                v = _lettres(m[1], self.cfg.lettres)
                garder(*m.span(), GenreNombre.NUM, str(v), self.unite(m[2]))
        for m in self.annee.finditer(texte):
            an = int(m[1])
            if libre(*m.span()) and self.cfg.annee_min <= an <= self.cfg.annee_max:
                garder(*m.span(), GenreNombre.DATE, f"{an:04d}", "date", PrecisionDate.ANNEE)
        for m in self.sans_unite.finditer(texte):
            if libre(*m.span()):
                garder(*m.span(), GenreNombre.NUM, _decimal(m[0]), "")
        return sorted(out, key=lambda n: n.debut)


def _date(an: int, mois: int, jour: int) -> bool:
    try:
        date(an, mois, jour)
    except ValueError:
        return False
    return True


_DETECTEURS: dict[int, _Detecteur] = {}


def nombres(
    texte: str, cfg: NombresConfig, exclus: list[tuple[int, int]] | None = None
) -> list[NombreLu]:
    """Nombres et dates du texte, dans l'ordre, hors des zones `exclus` (début, fin)."""
    d = _DETECTEURS.get(id(cfg))
    if d is None or d.cfg is not cfg:
        d = _DETECTEURS[id(cfg)] = _Detecteur(cfg)
    return d(texte, exclus or [])
