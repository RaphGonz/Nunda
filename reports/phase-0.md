# Rapport — Phase 0

Dépôt, configuration, CI, schémas de données (SPEC.md §2, §3, §4).

## Seuil contre mesure

| Seuil (SPEC.md §2) | Mesure | État |
| --- | --- | --- |
| `make test` passe sur une machine neuve | Clone neuf de `phase-0` : `make setup && make test` OK (35 tests, ruff OK). CI GitHub verte sur Ubuntu et Windows (commit `7f04c66`) | atteint |

## Livré

- `uv` + `uv.lock`, Python 3.11, `Makefile` (`setup`, `lint`, `test`), ruff, pytest, hypothesis.
- Squelette des paquets de SPEC.md §3 ; 8 configs YAML lues par pydantic (`ccm/config.py`) ; CLI typer vide.
- `ccm/schema.py` : énumérations (types de pièces, genres, types de noms, arêtes, contraintes), 24 relations avec leurs identifiants, lexique de 25 jetons, DDL du stock SQLite (`ouvrir_stock`, `secure_delete` actif), modèles pydantic de l'exemple JSON avec contrôles (marqueurs ⟦i⟧, relations par famille, pas de cible, justificatives).
- Exemple de SPEC.md §4 figé dans `tests/golden/exemple_spec.json` et validé.
- Test T7 (hors ligne) : garde réseau sur les modules d'inférence, contrôle statique des imports réseau.

## Écarts (tranchés par Raphael le 2026-10-14)
- `MarqueNombre` : `signe` obligatoire pour NUM et interdit pour DATE ; `precision` obligatoire pour DATE et interdite pour NUM (SPEC.md §6). L'exemple de SPEC.md §4 reçoit `"precision": "JOUR"`.
- `relations_props` : indices contrôlés contre les propositions présentes. L'exemple de SPEC.md §4 passe à `"relations_props": []` (il reliait 0 à 1 avec une seule proposition).
- Sens d'une relation orientée = ordre `(a, b)` du triplet ; l'identifiant inverse est déduit à l'encodage. Validé.

## Risques ouverts

- Aucune dépendance lourde installée (PyTorch, spaCy, GLiNER) : le temps d'installation et la CI Windows changeront aux phases 2 et 4.
- `make` sur la CI Windows vient de `choco install make`.

## Questions pour Raphael
1. §16 encore ouvert : heures et dépense maximale sur la RTX 3090 ; modèle enseignant 7B exact.
