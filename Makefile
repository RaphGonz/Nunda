.PHONY: setup lint test test-t11 test-complet nuit tableau eval nuit-a1 tableau-a1 eval-a1 pretrain-debit pretrain-chaine nuit-b courbe-b nuit-b-fin courbe-b-fin

# Sortie des scripts en UTF-8 (console cp1252 sous Windows).
export PYTHONUTF8 = 1

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
	uv run --locked python -m ccm.train.courbe

tableau:
	uv run --locked python -m ccm.train.tableau
	uv run --locked python -m ccm.train.courbe

eval:
	uv run --locked python -m ccm.eval.a0 >> runs/eval.log 2>&1

# A1 : une nuit (9 h), tableaux, puis mesures de fin quand les 2 époques sont faites.
nuit-a1:
	uv run --locked python -m ccm.train.a1 lancer >> runs/nuit-a1.log 2>&1
	uv run --locked python -m ccm.train.tableau a1
	uv run --locked python -m ccm.train.courbe a1
	uv run --locked python -m ccm.train.a1 evaluer >> runs/eval-a1.log 2>&1

tableau-a1:
	uv run --locked python -m ccm.train.tableau a1
	uv run --locked python -m ccm.train.courbe a1

eval-a1:
	uv run --locked python -m ccm.train.a1 evaluer >> runs/eval-a1.log 2>&1

# Corpus de pré-entraînement (§12) : après `ccm pretrain telecharger`, `brut` et `canaris`.
pretrain-debit:
	uv run --locked ccm pretrain debit >> runs/pretrain-debit.log 2>&1

pretrain-chaine:
	uv run --locked ccm pretrain chaine >> runs/pretrain-chaine.log 2>&1
	uv run --locked ccm pretrain bilan >> runs/pretrain-chaine.log 2>&1

# Pré-entraînement de B (§13) : une session de 8 h, reprise au dernier point de contrôle.
nuit-b:
	powershell -NoProfile -ExecutionPolicy Bypass -File runs/b-nuit-lancer.ps1

courbe-b:
	uv run --locked python -m ccm.train.courbe_b

# Réglage fin de B (phase 6) : une session de 8 h en tranches de 2 h, détachée.
nuit-b-fin:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','runs-fin-lancer.ps1'"

courbe-b-fin:
	uv run --locked python -m ccm.train.courbe b-fin
