"""Étapes 3 et 3 bis de l'ingestion : segmentation en propositions (SPEC.md §5).

Une proposition par phrase (pysbd, français ; les points des abréviations juridiques et
des initiales sont masqués avant la découpe, le texte n'est pas modifié). Un en-tête de
pièce (motif d'en-tête en capitales dans les premières lignes) reste une proposition
EN_TETE. Arêtes : SUIVANTE entre deux propositions qui se suivent ; DEPEND_DE (de la
phrase vers la précédente) si la phrase commence par un mot de la liste, a moins de
`mots_min` mots, ou répond à une question dans une audition. Une phrase de plus de
`mots_max` mots est coupée après les points-virgules et les deux-points : ses parties
ont le genre PARTIE et dépendent l'une de l'autre dans les deux sens.
"""

import re
from dataclasses import dataclass
from functools import cache

import pysbd

from ccm.config import IngestConfig, SegmentationConfig
from ccm.ingest.extract import paragraphes
from ccm.ingest.piece_type import PieceLue, motif_en_tete
from ccm.schema import GenreProposition, TypeArete, TypePiece

_MASQUE = ""  # remplace un point qui ne finit pas la phrase (même longueur)


@dataclass(frozen=True)
class PropLue:
    texte: str
    genre: GenreProposition
    page: int
    conf: float


@cache
def _segmenteur() -> pysbd.Segmenter:
    return pysbd.Segmenter(language="fr", clean=False, char_span=True)


@cache
def _abreviations(abreviations: tuple[str, ...]) -> re.Pattern:
    mots = "|".join(re.escape(a) for a in sorted(abreviations, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:(?:{mots})\.|(?:[A-ZÀ-Ý]\.)+)(?!\w)")


def _sans_blancs(texte: str, debut: int, fin: int) -> tuple[int, int]:
    while debut < fin and texte[debut].isspace():
        debut += 1
    while fin > debut and texte[fin - 1].isspace():
        fin -= 1
    return debut, fin


def phrases(texte: str, cfg: SegmentationConfig) -> list[tuple[int, int]]:
    """Position (début, fin) de chaque phrase dans le texte."""
    masque = _abreviations(cfg.abreviations).sub(lambda m: m[0].replace(".", _MASQUE), texte)
    spans = [_sans_blancs(texte, s.start, s.end) for s in _segmenteur().segment(masque)]
    return [(d, f) for d, f in spans if f > d]


def _parties(texte: str, debut: int, fin: int, cfg: SegmentationConfig) -> list[tuple[int, int]]:
    if len(texte[debut:fin].split()) <= cfg.mots_max:
        return [(debut, fin)]
    coupes = [debut] + [m.end() for m in re.compile(r"[;:]\s+").finditer(texte, debut, fin)]
    coupes.append(fin)
    spans = [_sans_blancs(texte, a, b) for a, b in zip(coupes, coupes[1:], strict=False)]
    return [(a, b) for a, b in spans if b > a]


def _depend(phrase: str, precedente: str | None, audition: bool, cfg: SegmentationConfig) -> bool:
    if precedente is None:
        return False
    if any(re.match(rf"{re.escape(m)}(?!\w)", phrase) for m in cfg.dependance_mots):
        return True
    if len(phrase.split()) < cfg.mots_min:
        return True
    return audition and (
        re.match(cfg.motif_reponse, phrase) is not None
        or re.match(cfg.motif_question, precedente) is not None
        or precedente.endswith("?")
    )


def segmenter(
    piece: PieceLue, cfg: IngestConfig
) -> tuple[list[PropLue], list[tuple[int, int, TypeArete]]]:
    """Propositions de la pièce et arêtes (indices dans la liste des propositions)."""
    props: list[PropLue] = []
    aretes: list[tuple[int, int, TypeArete]] = []
    audition = piece.type == TypePiece.PV_AUDITION
    premiere = piece.pages[0].numero
    precedente = None
    for par in paragraphes(piece.pages):
        en_tete = (
            par.page == premiere
            and par.ligne < cfg.pieces.lignes_en_tete
            and motif_en_tete(par.texte, cfg.pieces) is not None
            and not any(c.islower() for c in par.texte)
        )
        if en_tete:
            conf = par.conf(0, len(par.texte))
            props.append(PropLue(par.texte, GenreProposition.EN_TETE, par.page, conf))
            precedente = par.texte
            continue
        for d, f in phrases(par.texte, cfg.segmentation):
            ph = par.texte[d:f]
            depend = _depend(ph, precedente, audition, cfg.segmentation)
            parties = _parties(par.texte, d, f, cfg.segmentation)
            genre = GenreProposition.PARTIE if len(parties) > 1 else GenreProposition.PHRASE
            debut = len(props)
            for k, (a, b) in enumerate(parties):
                props.append(PropLue(par.texte[a:b], genre, par.page, par.conf(a, b)))
                if k:
                    aretes += [
                        (debut + k, debut + k - 1, TypeArete.DEPEND_DE),
                        (debut + k - 1, debut + k, TypeArete.DEPEND_DE),
                    ]
            if depend:
                aretes.append((debut, debut - 1, TypeArete.DEPEND_DE))
            precedente = ph
    aretes += [(k, k + 1, TypeArete.SUIVANTE) for k in range(len(props) - 1)]
    return props, aretes
