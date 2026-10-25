"""Étape 2 de l'ingestion : pièces et types (SPEC.md §5).

Un fichier est une pièce. Dans un fichier, une nouvelle pièce commence à chaque page dont
les `lignes_en_tete` premières lignes contiennent un motif d'en-tête. Le type est celui du
premier motif de la table trouvé dans ces lignes (AUTRE sinon) ; le rang vient de la table
type → rang (0 : non classé).
"""

import re
from dataclasses import dataclass

from ccm.config import PiecesConfig
from ccm.ingest.extract import Page, texte_ligne
from ccm.schema import TypePiece


@dataclass(frozen=True)
class PieceLue:
    pages: list[Page]
    type: TypePiece
    rang: int


def _tete(page: Page, cfg: PiecesConfig) -> list[str]:
    return [texte_ligne(d) for d in page.lignes[: cfg.lignes_en_tete]]


def motif_en_tete(texte: str, cfg: PiecesConfig) -> TypePiece | None:
    for m in cfg.motifs:
        if re.search(m.motif, texte):
            return m.type
    return None


def type_piece(page: Page, cfg: PiecesConfig) -> TypePiece | None:
    """Type du premier motif de la table trouvé en tête de page ; None sans motif."""
    tete = _tete(page, cfg)
    for m in cfg.motifs:
        if any(re.search(m.motif, s) for s in tete):
            return m.type
    return None


def decouper_pieces(pages: list[Page], cfg: PiecesConfig) -> list[PieceLue]:
    groupes: list[tuple[TypePiece, list[Page]]] = []
    for k, p in enumerate(pages):
        t = type_piece(p, cfg)
        if k == 0 or t is not None:
            groupes.append((t or TypePiece.AUTRE, [p]))
        else:
            groupes[-1][1].append(p)
    return [PieceLue(ps, t, cfg.rang.get(t, 0)) for t, ps in groupes]
