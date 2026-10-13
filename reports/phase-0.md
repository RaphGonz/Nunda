# Rapport — Phase 0

Dépôt, configuration, CI, schémas de données (SPEC.md §2, §3, §4).

## Seuil contre mesure

| Seuil (SPEC.md §2) | Mesure | État |
| --- | --- | --- |
| `make test` passe sur une machine neuve | Clone neuf de `phase-0` : `make setup && make test` OK (26 tests, ruff OK). CI GitHub verte sur Ubuntu et Windows (commit `63b310d`) | atteint |

## Livré

- `uv` + `uv.lock`, Python 3.11, `Makefile` (`setup`, `lint`, `test`), ruff, pytest, hypothesis.
- Squelette des paquets de SPEC.md §3 ; 8 configs YAML lues par pydantic (`ccm/config.py`) ; CLI typer vide.
- `ccm/schema.py` : énumérations (types de pièces, genres, types de noms, arêtes, contraintes), 24 relations avec leurs identifiants, lexique de 25 jetons, DDL du stock SQLite (`ouvrir_stock`, `secure_delete` actif), modèles pydantic de l'exemple JSON avec contrôles (marqueurs ⟦i⟧, relations par famille, pas de cible, justificatives).
- Exemple de SPEC.md §4 figé dans `tests/golden/exemple_spec.json` et validé.

## Écarts

- `MarqueNombre` a deux champs optionnels absents de l'exemple JSON : `signe` (-1, 0, 1) et `precision` (JOUR, MOIS, ANNEE). SPEC.md §6 en fait des entrées du modèle, et l'exemple JSON est la seule entrée.
- Les indices de `relations_props` ne sont pas contrôlés contre les propositions présentes : l'exemple de SPEC.md §4 relie les propositions 0 et 1 alors qu'il n'en contient qu'une.
- Le sens d'une relation orientée est donné par l'ordre `(a, b)` du triplet ; le JSON ne porte pas l'identifiant inverse.

## Risques ouverts

- Aucune dépendance lourde installée (PyTorch, spaCy, GLiNER) : le temps d'installation et la CI Windows changeront aux phases 2 et 4.
- `make` sur la CI Windows vient de `choco install make`.

## Questions pour Raphael

1. Valider les champs `signe` et `precision` de `MarqueNombre`, ou corriger l'exemple de SPEC.md §4.
2. L'exemple de SPEC.md §4 est-il tronqué (proposition 1 absente) ? Si oui, le contrôle des indices de `relations_props` peut être ajouté.
3. §16 encore ouvert : heures et dépense maximale sur la RTX 3090 ; modèle enseignant 7B exact.
