"""Attributs d'un nombre ou d'une date (SPEC.md §6).

NUM : ordre de grandeur (partie entière de log10 de la valeur absolue, bornée ; None pour
zéro), rang dense parmi les valeurs de même unité du contexte (borné), signe. DATE :
rang chronologique ; ni ordre de grandeur (il donnerait l'année), ni signe. Les valeurs
se comparent en décimal exact ; une date est une date ISO (« 2024 » < « 2024-12-07 »).
"""

from decimal import Decimal

from ccm.config import AnonymiseurConfig


def cle_valeur(genre: str, valeur: str) -> str:
    """Même clé pour deux valeurs égales (« 1250.00 » et « 1250 »)."""
    return valeur if genre == "DATE" else str(Decimal(valeur).normalize())


def _ordre(genre: str, valeur: str):
    return valeur if genre == "DATE" else Decimal(valeur)


def attributs(
    valeurs: list[tuple[str, str, str]], cfg: AnonymiseurConfig
) -> list[tuple[int | None, int, int | None]]:
    """(genre, valeur, unité) → (grandeur, rang, signe), dans l'ordre reçu."""
    par_unite: dict[str, set] = {}
    for g, v, u in valeurs:
        par_unite.setdefault(u, set()).add(_ordre(g, v))
    rangs = {u: {x: k for k, x in enumerate(sorted(xs))} for u, xs in par_unite.items()}
    lo, hi = cfg.grandeur
    out = []
    for g, v, u in valeurs:
        rang = min(rangs[u][_ordre(g, v)], cfg.rang_max)
        if g == "DATE":
            out.append((None, rang, None))
            continue
        d = Decimal(v)
        grandeur = None if d == 0 else max(lo, min(hi, d.adjusted()))
        out.append((grandeur, rang, (d > 0) - (d < 0)))
    return out
