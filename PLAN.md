# Plan

Ordre des phases et seuils : SPEC.md §2 (ne change pas sans accord de Raphael).
Une branche `phase-N` par phase ; étiquette `phase-N-ok` quand le seuil passe.

| Phase | Contenu | Seuil de passage | État |
| --- | --- | --- | --- |
| 0 | Dépôt, configuration, CI, schémas de données | `make test` passe sur une machine neuve | fait (`phase-0-ok`) |
| 1 | Générateur de monde, corpus synthétique niveau 0 (gabarits) | contrôle à 100 % ; même graine, mêmes fichiers | en cours |
| 2 | Ingestion, graphe, anonymiseur, recherche | rappel PER ≥ 0,98 ; rappel justificatives ≥ 0,95 ; T2 exact ; conflits établis : précision ≥ 0,9, rappel ≥ 0,5 (heure, montant) | à faire |
| 3 | Grammaire, automate, vérificateur, rendu, oracle | suites de référence acceptées à 100 % ; 100 000 décodages valides ; aucun affichage hors contexte | à faire |
| 4 | Prototypes A0 puis A1 | A0 niveau 0 : F1 citation ≥ 0,90, abstention ≥ 0,85 ; HotpotQA F1 faits ≥ 0,75 | à faire |
| 5 | Pré-entraînement de B | T1 exact ; perte stable ; canaris mesurés | à faire |
| 6 | Réglage fin de B, comparaisons, ablations | B ≥ 95 % du F1 de citation de A1 | à faire |
| 7 | Niveaux de dégradation 1 à 5 | mesures publiées par niveau | à faire |

## Phase 0

- [x] `uv` + `uv.lock`, Python 3.11, `Makefile` (`setup`, `test`, `lint`), ruff, pytest, hypothesis
- [x] Configs YAML lues par pydantic (`ccm/config.py`), CLI typer vide, CI GitHub Actions
- [x] Squelette des paquets de SPEC.md §3
- [x] `ccm/schema.py` : contrats de données (SPEC.md §4)
- [x] CI verte sur GitHub (Ubuntu + Windows)
- [x] Rapport `reports/phase-0.md`
