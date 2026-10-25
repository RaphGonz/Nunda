.PHONY: setup lint test

setup:
	uv sync --locked
	uv run --locked ccm modeles

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

test: lint
	uv run --locked pytest
