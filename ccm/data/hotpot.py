"""HotpotQA, réglage « distracteurs » (SPEC.md §12) : une phrase = une proposition ; phrase
justificative = CITE, dans l'ordre du jeu ; la réponse courte est ignorée."""

from collections.abc import Iterator
from pathlib import Path

import pyarrow.parquet as pq

from ccm.data.publics import Brut


def brut_de(ligne: dict) -> Brut:
    titres, phrases = ligne["context"]["title"], ligne["context"]["sentences"]
    paragraphes, indices = [], {}
    for titre, ps in zip(titres, phrases, strict=True):
        garde = {j: p.strip() for j, p in enumerate(ps) if p.strip()}
        for k, j in enumerate(garde):
            indices[(titre, j)] = (len(paragraphes), k)
        paragraphes.append(list(garde.values()))
    sf = ligne["supporting_facts"]
    # Une justificative qui ne pointe sur aucune phrase devient hors du contexte (rejet).
    justifs = [indices.get((t, j), (len(paragraphes), 0))
               for t, j in zip(sf["title"], sf["sent_id"], strict=True)]  # fmt: skip
    return Brut(f"hotpot-{ligne['id']}", "hotpot", "en", ligne["question"].strip(), paragraphes,
                justifs, temoins=list(titres))  # fmt: skip


def lire(dossier: Path, partie: str) -> Iterator[Brut]:
    """`partie` : train ou validation."""
    for f in sorted(dossier.glob(f"{partie}-*.parquet")):
        for lot in pq.ParquetFile(f).iter_batches(batch_size=1000):
            yield from map(brut_de, lot.to_pylist())
