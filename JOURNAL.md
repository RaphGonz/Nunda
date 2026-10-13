# Journal du projet CCM

Une entrée par séance, la plus récente en bas. Modèle :

```
## AAAA-MM-JJ — Phase N — <titre court>
- **Travail fait :**
- **Mesures :**
- **Décisions :**
- **Écarts avec SPEC.md :**
- **Suite prévue :**
```

Un arrêt (SPEC.md §15) s'écrit dans une entrée avec une ligne **ARRÊT :** qui donne le cas (1 à 4) et le problème.

---

## 2026-10-13 — Phase 0 — Mise en place du dépôt
- **Travail fait :** dépôt git créé (GitHub privé `Nunda`), `CLAUDE.md`, `JOURNAL.md`, `.gitignore`. Aucun code.
- **Mesures :** aucune.
- **Décisions :** le dépôt est à la racine de `Nunda/` ; le paquet Python sera `ccm/` (SPEC.md §3).
- **Écarts avec SPEC.md :** aucun. `make` installé via winget (`ezwinports.make`, GNU Make 4.4.1) ; `make test` attend le `Makefile` de la phase 0.
- **Suite prévue :** phase 0 (SPEC.md §2, §3, §4) : `pyproject.toml` avec `uv`, `Makefile` (`make test` = `ruff` + `pytest`), squelette des modules, `ccm/schema.py`, CI verte.

## 2026-10-13 — Phase 0 — Squelette du dépôt, outillage, CI
- **Travail fait :** `pyproject.toml` + `uv.lock` (Python 3.11 figé par `.python-version`), `Makefile` (`setup`, `lint`, `test` = ruff check + ruff format --check + pytest), squelette des paquets de SPEC.md §3 (`ccm/ingest`, `ner`, `graph`, `search`, `anonymize`, `grammar`, `model`, `verify`, `data/worldgen`, `train`, `eval`), `tests/unit|property|golden`, 8 configs YAML lues par `ccm/config.py` (pydantic, clé inconnue refusée), CLI typer vide (`ccm --help`), CI GitHub Actions (Ubuntu + Windows, `make setup` puis `make test`). Ajout de `PLAN.md`, `README.md`, `DATA_LICENSES.md` (vide). `SPEC.md` déjà présent.
- **Mesures :** `make test` local : ruff OK, 12 tests passés.
- **Décisions :**
  - SPEC.md §16, prises par Raphael : **budget de calcul : GPU RTX 3090** (heures et dépense maximale pas encore fixées) ; **modèle de base de A : SmolLM** ; **modèle enseignant : LLM local de 7B** (phase 4 Légifrance et phase 7 rédaction des pièces ; modèle exact à choisir, licence à vérifier dans `DATA_LICENSES.md`).
  - Le dossier `ccm/` racine de SPEC.md §3 est la racine du dépôt `Nunda/` (décision de la séance précédente).
  - Dépendances de la séance seulement : pydantic, pyyaml, typer ; dev : ruff, pytest, hypothesis. PyTorch et les autres arrivent avec la phase qui les utilise.
  - Configs : champs `version` et `description` seulement ; chaque phase ajoute ses champs. `model_a0/a1/b_s/b_m` partagent la classe `ModelConfig` pour l'instant.
  - Sous-paquets créés avec `__init__.py` seul ; les modules (`extract`, `bm25`…) s'écrivent avec leur phase.
  - CI Windows : `make` installé par `choco install make`.
- **Écarts avec SPEC.md :** aucun. `schema.py` pas encore écrit (pas dans la tâche du soir).
- **Suite prévue :** `ccm/schema.py` (SPEC.md §4), vérifier la CI verte sur GitHub, puis `reports/phase-0.md`.
