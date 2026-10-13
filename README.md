# CCM — modèle de citation amnésique

`SPEC.md` fait foi. Plan des phases : `PLAN.md`. Journal des séances : `JOURNAL.md`.

## Installation

Prérequis : [`uv`](https://docs.astral.sh/uv/) et GNU Make.

```
make setup   # installe Python 3.11 et les dépendances figées (uv.lock)
make test    # ruff + pytest
make lint    # ruff seul
```

Commande : `uv run ccm --help`.
