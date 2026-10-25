# Rapport — Phase 2
Ingestion, graphe, anonymiseur, recherche (SPEC.md §2, §5, §6, §7). Commandes `ingest`, `search`, `anonymize` (et `forget`).

## Seuil contre mesure
Réglage sur la validation (200 dossiers) ; mesure finale une seule fois sur le test (200 dossiers, gabarits propres), le 2026-10-25, code de `phase-2`.

| Seuil (SPEC.md §2) | Validation | Test (final) | État |
| --- | --- | --- | --- |
| Rappel des noms PER ≥ 0,98 | 0,998 | **0,9973** (22 212 mentions) | atteint |
| Rappel des propositions justificatives dans le budget ≥ 0,95 | 0,998 | **0,9966** (7 123 questions, 11 090 justificatives) | atteint |
| Test T2 exact | exact (3 dossiers, CI) | — (test de CI) | atteint |
| Conflits établis, heure et montant : précision ≥ 0,9 | 0,970 (code actuel ; 0,985 le 2026-10-21) | **0,807** (46 VP, 11 FP) | **non atteint** |
| Conflits établis, heure et montant : rappel ≥ 0,5 | 0,80 | **0,687** (HEURE 38/45, MONTANT 8/22) | atteint |

`make test` : 208 tests passés. Mesures : `runs/final/bilan.json` (`ccm.eval.noms`, `ccm.eval.conflits`, `ccm.eval.recherche`, un processus chacun).

Détail du test :
- Noms : ORG 0,9987, LIEU 1,0, REF 1,0 ; précision des zones 0,854 ; manques : surnoms à article (« le Toubib », « le Rital », « la Fouine »).
- Recherche, par type : PLUSIEURS_ETAPES 0,9912, tous les autres 1,0. Contexte moyen : 76 propositions, environ 2 160 jetons (65 % du stock d'un dossier). Budget serré à 1 000 jetons (validation) : 0,9425, PLUSIEURS_ETAPES 0,864.
- Conflits avec les mentions de référence à la place des détecteurs : précision 0,797. La baisse ne vient donc pas de la détection des noms.

## Le seuil non atteint
La règle des conflits (§5) a été réglée sur la validation, qui partage les gabarits de l'entraînement. Sur la validation remesurée avec le code actuel, elle donne 0,970 ; sur le test, 0,807. L'écart vient des gabarits propres au test : la règle colle aux formulations de l'entraînement. Je n'ai pas regardé les faux positifs du test (interdit : régler une règle en regardant les résultats de test).

## Écarts avec SPEC.md
- Extraction par pypdfium2 au lieu de PyMuPDF (décision de Raphael, 2026-10-18).
- Conflits PERSONNE hors du seuil (niveau 1, décision de Raphael) : 0/84 sur le test.
- Jetons de la recherche estimés (4 + 1,6 × mots) en attendant le tokenizer.

## Risques ouverts
- Le niveau 0 est petit : la recherche prend 65 % d'un dossier, son rappel dit peu du classement.
- Faux positifs des noms (en-têtes de PV, « Le témoin », « le Commissaire ») : précision des zones 0,85.
- Surnoms à article non détectés (rappel PER des messages en minuscules 0,986).

## Questions pour Raphael
1. **Précision des conflits sur le test : 0,807 < 0,9.** Que faire ?
   (a) Créer un second jeu de validation avec des gabarits nouveaux, ni d'entraînement ni de test, régler la règle dessus, puis refaire une seule mesure sur le test (il faudra alors un nouveau test, celui-ci ayant servi). Recommandé.
   (b) Accepter 0,807 et clore la phase avec cet écart écrit.
   (c) Baisser le seuil (changement de seuil : ta décision).
2. Garder la mesure de la recherche à 1 000 jetons comme contrôle du classement ?
