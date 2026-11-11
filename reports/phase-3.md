# Rapport — Phase 3
Grammaire, automate, vérificateur, rendu, modèle oracle (SPEC.md §2, §10, §10 bis, §11). Commande `ccm answer --oracle` de bout en bout. Rapport écrit le 2026-11-11, à la clôture de la phase 4 (la phase 3 n'avait pas été close à temps).

## Seuil contre mesure
| Seuil (SPEC.md §2) | Mesure | État |
| --- | --- | --- |
| 100 % des suites de référence acceptées par l'automate | Corpus niveau 0 (2026-10-26) : entraînement 79 953 / 79 953 (citation) et 71 158 / 71 158 (synthèse) ; validation 8 000 / 8 000 et 7 141 / 7 141 ; test 7 982 / 7 982 et 7 123 / 7 123. 0 refus. | atteint |
| 100 000 décodages aléatoires sous masque, tous valides | `ccm.eval.grammaire` : 100 540 / 100 540, aucune impasse (2026-10-25). T11, synthèse : 100 925 / 100 925, 0 erreur du vérificateur (2026-10-28). | atteint |
| Aucun nom, nombre ou date affiché hors du contexte | T5 : 0 fragment hors des ensembles permis, sur les décodages au hasard et les suites de référence ; tests figés de `ccm answer --oracle` (40 questions × 2 modes), chaque fragment contrôlé. | atteint |

`make test-complet` (2026-11-11, code de `phase-4`, qui contient la phase 3) : 374 passés, et T11 passé.

Modèle oracle sur 10 dossiers de validation : 740 / 802 réponses rejouées (92,3 %), 0 erreur du vérificateur. Les 62 abstentions viennent surtout de faits non détectés par la vraie détection des noms (58).

## Livrables
`ccm/grammar/` (lexique, algèbre des unités, automate et masque), `ccm/verify/` (vérificateur, étapes 1 à 9 ; rendu à gabarits fixes ; trace), `ccm/model/oracle.py`, `ccm/answer.py`, `ccm answer --oracle`, `demo/demo.py` (9 scènes), suites de référence du corpus (`ccm/data/worldgen/suites.py`), tests T4, T5, T9, T10, T11 et tests figés. Hors du périmètre de la phase, mais faits pendant elle : `ccm/anonymize/encode.py` (§8) et les jeux publics du §12.

## Écarts avec SPEC.md
- T5 : la pièce, la page, le rang et le numéro de citation forment une cinquième origine (« ref »). Validé par Raphael le 2026-10-27, SPEC.md §11 mis à jour.
- CALCUL : un même nombre peut être repris (décision de Raphael). DATE + DATE est interdit. `pas_max_synthese` vaut 512.
- Exemple de §4 corrigé (`P:0 ET SAME …`), avec l'accord de Raphael (2026-10-30).
- `ccm/answer.py` et `demo/` ne sont pas dans l'arbre de §3.
- T11 est sorti de `make test` (mémoire) ; il tourne dans `make test-complet` et en CI.
- Vocabulaire V de la synthèse provisoire (mots des synthèses de référence) jusqu'à la phase 5.

## Risques ouverts
- `seuil_selection` = 0,5 (passages non cités) n'est pas encore réglé sur la validation.
- Refus de l'automate non analysé : `syn-1000009-q20` (`M:19.2` refusé à l'état M2).
- La synthèse n'est pas dans `encode` (`Exemple.cible` refuse `W:`), à reprendre en phase 4 bis.

## Questions pour Raphael
1. Exclure les « il » impersonnels (« Il ressort », « Il est établi », « Il apparaît ») de la liste de DEPEND_DE (§5, étape 3) ? Aujourd'hui, le vérificateur affiche la phrase précédente en « Contexte : », même quand elle parle d'un autre événement. Question posée le 2026-10-29, toujours sans réponse.
