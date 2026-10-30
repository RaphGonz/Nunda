.PHONY: setup lint test test-t11 test-complet

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
