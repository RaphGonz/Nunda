# CLAUDE.md — projet CCM (Nunda)

Tu travailles sur le projet CCM (modèle de citation amnésique).
`SPEC.md` fait foi. Applique les règles de sa section 15 (« Règles pour l'agent »).
Si SPEC.md ne dit rien, prends l'option la plus simple et écris-la au journal.

## Avant de commencer
1. Lis `JOURNAL.md`, puis les sections de `SPEC.md` citées dans la tâche du soir.
   La tâche du soir est celle que Raphael donne dans son message. S'il n'en donne pas,
   c'est la « Suite prévue » de la dernière entrée de `JOURNAL.md`.
2. Travaille sur la branche de la phase en cours (`phase-N`). Crée-la depuis `main`
   si elle n'existe pas. Ne travaille jamais directement sur `main`.
3. Fais seulement la tâche de ce soir. Ne commence pas la suivante.

## À la fin
4. Lance `make test`. Tous les tests doivent passer. `make test` exclut T11 (coûteux).
   Lance `make test-complet` si le travail touche `grammar`, `verify`, `anonymize`
   (hors `encode`), `ingest` ou `worldgen`, et toujours avant de clore une phase.
5. Fais de petits commits avec des messages clairs.
6. Ajoute une entrée dans `JOURNAL.md` (modèle en tête du fichier) : date, phase,
   travail fait, mesures, décisions, écarts avec SPEC.md, suite prévue.
7. Pousse la branche sur `origin`.

## Cas d'arrêt (SPEC.md §15)
Arrête-toi et écris le problème dans `JOURNAL.md` si :
1. un seuil de phase n'est pas atteint après trois essais documentés ;
2. un test de garantie (T1, T2, T4, T5, T8) échoue et sa correction demande de changer une règle ;
3. une licence de données n'est pas claire, ou interdit l'usage prévu ;
4. une durée mesurée dépasse 5 jours, ou le budget de calcul fixé.

## Ne change jamais sans accord de Raphael
- Le lexique, la grammaire, la liste des 24 relations, les règles du vérificateur.
- Le texte d'une garantie, ou le résultat attendu d'un test T1 à T10.
- L'usage de toute donnée personnelle réelle ; l'envoi de toute donnée non publique à un service externe.
- L'ordre des phases et leurs seuils.

## Ne fais jamais
- Affaiblir un test, ou changer une donnée de référence, pour passer un seuil.
- Entraîner sur un dossier de test, ou régler un gabarit en regardant les résultats de test.
- Écrire une chaîne de nom dans un fichier d'entraînement.
- Mettre un modèle génératif dans `ingest`, `search`, `anonymize` ou `verify`.

## Fin de phase
- Écris `reports/phase-N.md` : tableau seuil contre mesure, écarts, risques ouverts, questions pour Raphael.
- Quand le seuil passe : étiquette `phase-N-ok`, fusion de `phase-N` dans `main`, push des deux et de l'étiquette.

## Environnement
- Windows 10. GNU Make 4.4.1 installé via winget (`ezwinports.make`).
- Python via `uv` (versions figées dans `uv.lock`). Règles de code : SPEC.md §3.
- `runs/` reste hors de git.
