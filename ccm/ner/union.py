"""Union des détecteurs et limites d'un nom (SPEC.md §6).

Union : deux zones qui se chevauchent fusionnent en une zone qui couvre les deux ; son
type est le plus prioritaire (REF, PER, ORG, LIEU, AUTRE). Limites : deux zones séparées
seulement par des blancs ou des particules (« Jean de La Fontaine ») forment un seul nom ;
les titres en tête (M., Mme, Maître, grades) restent du texte, hors de la zone. Une zone
ne franchit jamais une séparation de cellules « | » (étape 4) ; les mots sans lettre en
bord d'une zone de nom en sortent (une date, un montant voisins), sauf un numéro en tête
suivi d'un mot en minuscules autre qu'un mois (« 103 rue de la Poste ») ou en tête d'une
zone LIEU. Une zone de nom sans aucune majuscule n'est pas gardée (un montant
lu MISC par spaCy n'est pas un nom) ; une référence est toujours gardée.
"""

import re

from ccm.anonymize.names import norme
from ccm.config import IngestConfig, NomsConfig
from ccm.ner.detectors import Zone, d1_gliner, d2_spacy, d3_regles, d4_majuscules
from ccm.schema import TypeNom

_PRIORITE = {t: k for k, t in enumerate(TypeNom)}


def _type(a: TypeNom, b: TypeNom) -> TypeNom:
    return min(a, b, key=_PRIORITE.__getitem__)


def _fusion(a: Zone, b: Zone) -> Zone:
    return Zone(
        min(a.debut, b.debut), max(a.fin, b.fin), _type(a.type, b.type), a.detecteurs | b.detecteurs
    )


def unir(zones: list[Zone]) -> list[Zone]:
    out: list[Zone] = []
    for z in sorted(zones, key=lambda z: (z.debut, -z.fin)):
        if out and z.debut < out[-1].fin:
            out[-1] = _fusion(out[-1], z)
        else:
            out.append(z)
    return out


def _sans_titre(texte: str, z: Zone, cfg: NomsConfig) -> Zone | None:
    debut = z.debut
    while m := re.match(r"\S+\s+", texte[debut : z.fin]):
        if norme(m.group(), cfg).rstrip(".") not in cfg.titres:
            break
        debut += m.end()
    if norme(texte[debut : z.fin], cfg).rstrip(".") in cfg.titres:
        return None
    return Zone(debut, z.fin, z.type, z.detecteurs)


def _en_tete_hors_nom(mots: list[str], mois: tuple[str, ...]) -> bool:
    """Le premier mot sort de la zone : un mois, ou un mot sans lettre qui n'est pas un
    numéro de rue (« 103 rue … » : suivi d'un mot en minuscules autre qu'un mois)."""
    if mots[0] in mois:
        return True
    suivant = mots[1] if len(mots) > 1 else ""
    adresse = suivant[:1].islower() and suivant not in mois
    return not _lettre(mots[0]) and not adresse


def _lettre(mot: str) -> bool:
    return any(c.isalpha() for c in mot)


def _decouper(texte: str, z: Zone, mois: tuple[str, ...]) -> list[Zone]:
    """Parties de la zone entre les « | », sans les mots hors nom en bord de zone."""
    out = []
    for m in re.finditer(r"[^|]+", texte[z.debut : z.fin]):
        d = z.debut + m.start()
        mots = [(d + w.start(), d + w.end()) for w in re.finditer(r"\S+", m.group())]
        if z.type != TypeNom.REF:
            while mots and not _lettre(texte[mots[-1][0] : mots[-1][1]]):
                mots.pop()
            while (
                mots
                and z.type != TypeNom.LIEU
                and _en_tete_hors_nom([texte[a:b] for a, b in mots[:2]], mois)
            ):
                mots.pop(0)
        if mots:
            out.append(Zone(mots[0][0], mots[-1][1], z.type, z.detecteurs))
    return out


def limites(
    texte: str, zones: list[Zone], cfg: NomsConfig, mois: tuple[str, ...] = ()
) -> list[Zone]:
    particules = "|".join(re.escape(p) for p in cfg.particules if p != "d")
    lien = re.compile(rf"[ \t]+(?:(?:{particules})[ \t]+)*|[ \t]+d['’]", re.IGNORECASE)
    out: list[Zone] = []
    for z in (p for u in unir(zones) for p in _decouper(texte, u, mois)):
        if (
            out
            and TypeNom.REF not in (z.type, out[-1].type)
            and lien.fullmatch(texte[out[-1].fin : z.debut])
        ):
            out[-1] = _fusion(out[-1], z)
        else:
            out.append(z)
    gardees = []
    for z in out:
        if z.type != TypeNom.REF:
            z = _sans_titre(texte, z, cfg)
            if z is None or not any(c.isupper() for c in texte[z.debut : z.fin]):
                continue
        gardees.append(z)
    return gardees


def detecter(textes: list[str], cfg: IngestConfig) -> list[list[Zone]]:
    """Zones de noms de chaque texte : union des détecteurs choisis, puis limites."""
    det = cfg.detection
    par: list[list[Zone]] = [[] for _ in textes]
    if "gliner" in det.detecteurs:
        for i, zs in enumerate(d1_gliner(textes, det.gliner)):
            par[i] += zs
    if "spacy" in det.detecteurs:
        for i, zs in enumerate(d2_spacy(textes, det.spacy)):
            par[i] += zs
    for i, t in enumerate(textes):
        if "regle" in det.detecteurs:
            par[i] += d3_regles(t, det, cfg.nombres)
        if "majuscules" in det.detecteurs:
            par[i] += d4_majuscules(t, det)
    return [limites(t, zs, cfg.noms, cfg.nombres.mois) for t, zs in zip(textes, par, strict=True)]
