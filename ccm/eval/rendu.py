"""Contrôle du rendu fermé (SPEC.md §11, test de propriété ; T5) : chaque fragment affiché
vient de l'un des quatre ensembles (texte original d'une proposition du contexte, de ses
dépendances et conflits ; gabarit fixe ; nom d'une mention du contexte ou des messages ;
résultat d'un calcul), ou des références lues dans le stock. Partagé par T5, T11 et les
tests figés de `ccm answer`."""

import re

from ccm.verify.render import PIECES_FIXES

_UNITES = r"(?: (?:€|%|km|kg|g|m|mois|ans?|jours?|heures?|minutes?))?"
_CALCUL = re.compile(
    rf"(?:≈ )?−?\d{{1,3}}(?: \d{{3}})*(?:,\d+)?{_UNITES}|\d\d/\d\d/\d{{4}}|\d\d/\d{{4}}|\d{{4}}"
    r"|\d{1,2} h \d\d"
)


def fermes(con, ex, entree):
    """Les quatre ensembles (et les références du stock) d'un exemple."""
    ids = {p.prop_id for p in ex.propositions}
    pile = list(ids)
    while pile:  # dépendances, toute la base
        for (d,) in con.execute("SELECT dst FROM arete WHERE src = ? AND type = 'DEPEND_DE'",
                                (pile.pop(),)):  # fmt: skip
            if d not in ids:
                ids.add(d)
                pile.append(d)
    ids |= {d for p in list(ids) for (d,) in con.execute(
        "SELECT dst FROM arete WHERE src = ? AND type = 'CONFLIT'", (p,))}  # fmt: skip
    marques = ",".join("?" * len(ids))
    textes = [t for (t,) in con.execute(
        f"SELECT texte FROM proposition WHERE prop_id IN ({marques})", list(ids))]  # fmt: skip
    noms = {s for (s,) in con.execute(
        f"SELECT surface FROM mention WHERE prop_id IN ({marques})", list(ids))}  # fmt: skip
    for m in (entree.question, *entree.historique):
        noms |= {m.texte[d:f] for d, f, _ in m.noms}
    refs = {r for row in con.execute(
        f"SELECT p.piece_id, p.page, c.rang FROM proposition p JOIN piece c USING (piece_id) "
        f"WHERE p.prop_id IN ({marques})", list(ids)) for r in map(str, row)}  # fmt: skip
    return textes, noms, refs


def controler(rep, textes, noms, refs, vocabulaire=frozenset()):
    assert rep.erreur is None, rep.erreur
    for b in rep.blocs:
        for f in b.frags:
            if f.genre == "gabarit":
                assert f.texte in PIECES_FIXES, f
            elif f.genre == "texte":
                assert any(f.texte in t for t in textes), f
            elif f.genre == "nom":
                assert f.texte in noms, f
            elif f.genre == "calcul":
                assert _CALCUL.fullmatch(f.texte), f
            elif f.genre == "ref":
                assert f.texte in refs or f.texte.isdigit(), f
            elif f.genre == "mot":
                assert f.texte.lower() in vocabulaire and not re.search(r"\d", f.texte), f
            else:
                raise AssertionError(f"fragment hors des quatre ensembles : {f}")
