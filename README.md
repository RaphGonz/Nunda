# CCM — modèle de citation amnésique

`SPEC.md` fait foi. Plan des phases : `PLAN.md`. Journal des séances : `JOURNAL.md`.

## Installation

Prérequis : [`uv`](https://docs.astral.sh/uv/) et GNU Make.

```
make setup   # installe Python 3.11 et les dépendances figées (uv.lock)
make test    # ruff + pytest, sans T11
make test-t11      # T11 seul (100 000 décodages, long et gourmand en mémoire)
make test-complet  # make test, puis T11 dans un second processus (CI)
make lint    # ruff seul
```

Commande : `uv run ccm --help`.

## Licence
Code sous licence MIT (`LICENSE`). Dépendances sous leur propre licence ; à noter : `ccm/data/worldgen` (générateur du corpus synthétique) utilise PyMuPDF, sous AGPL 3.0 : qui redistribue ce module avec PyMuPDF doit en respecter les conditions. Modèles et données : https://huggingface.co/RaphGonz (licences sur chaque fiche).
