.PHONY: setup lint test test-t11 test-complet nuit tableau eval

setup:
	uv sync --locked
	uv run --locked ccm modeles

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

# Sans les tests marqués `couteux` (T11, 100 000 décodages) : voir pyproject.toml.
test: lint
	uv run --locked pytest

test-t11:
	uv run --locked pytest -m couteux

# Deux processus l'un après l'autre : la mémoire du premier est rendue avant T11.
test-complet:
	$(MAKE) test
	$(MAKE) test-t11

# Une nuit d'entraînement de A0 (une époque, environ 8 à 9 h), puis les tableaux (§13).
nuit:
	uv run --locked python -m ccm.train.a0 lancer >> runs/nuit.log 2>&1
	uv run --locked python -m ccm.train.tableau

tableau:
	uv run --locked python -m ccm.train.tableau

eval:
	uv run --locked python -m ccm.eval.a0 >> runs/eval.log 2>&1
