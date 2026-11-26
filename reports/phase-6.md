# Rapport — Phase 6
Réglage fin de B-S sur la tâche de citation, comparaison avec A0 et A1 (SPEC.md §2, §13, §14). B-S : 110 M paramètres, pré-entraîné de zéro en phase 5 sur le corpus anonymisé. Une RTX 3090. Rapport écrit le 2026-11-26.

## Seuil contre mesure
Mêmes exemples de validation pour les trois modèles : corpus corrigé de la phase 4 (827 synthétiques de niveau 0, 999 HotpotQA à distracteurs) ; décodage glouton sous le masque (`ccm.eval.a0`, variante `b`).

| Seuil (SPEC.md §2) | Mesure | État |
| --- | --- | --- |
| B atteint au moins 95 % du F1 de citation de A1 sur le niveau 0 | B 0,845 ; A1 0,872 : **96,9 %** | **atteint** |

## Résultats
| Modèle | Point | F1 niveau 0 | Exactes | Abstention | F1 HotpotQA | Abst. à tort (HotpotQA) | Hors limite |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A0 | `2026-11-06-a0/pas-018124.pt` | 0,864 | 0,803 | 0,978 | 0,676 | 0,146 | 0 |
| A1 | `2026-11-08-a1/pas-008378.pt` | 0,872 | 0,819 | 0,989 | 0,748 | 0,043 | 0 |
| B-S | `2026-11-25-b-fin/pas-020625.pt` | 0,845 | **0,827** | 0,950 | **0,769** | **0,024** | 46 |

- **HotpotQA : B fait mieux que A1** (+0,021 de F1) et s'abstient à tort deux fois moins (2,4 % contre 4,3 %), avec 3 fois moins de paramètres et sans jamais avoir vu un nom en clair.
- **Niveau 0 : B est un peu en dessous de A1**, à cause des exemples trop longs. B ne lit que 2 048 jetons (positions vues au pré-entraînement) : 46 exemples dépassent (40 synthétiques, 6 HotpotQA) et comptent faux. Sur les exemples dans la limite, F1 0,891 au niveau 0 et 0,775 sur HotpotQA.
- Suites exactes au niveau 0 : B 0,827, meilleur des trois.
- Conflits (35 exemples) : F1 0,700 (A1 0,681) ; contrefactuels : 0,907 (A1 0,988).
- Abstention au niveau 0 : 0,950 (A1 0,989) ; B répond un peu plus souvent quand il faudrait s'abstenir.
- Détail par source et par genre : `runs/2026-11-25-b-fin/eval-pas-020625-corrige/rapport.md`.

## Exemples de réponses
`ccm.eval.comparer` (`exemples.json`, dans la page) : un conflit synthétique (deux témoignages d'heures différentes) où B cite la bonne paire et A0 et A1 une phrase voisine ; une question HotpotQA où A0 s'abstient et où A1 et B citent les deux phrases justificatives. Une réponse est une suite d'actions (citer P:n, ET, CONFLIT…, FIN), jamais du texte libre.

## Entraînement
- **Données :** tirages préchargés de A0 (5 époques), encodés de nouveau pour B (BPE de B, slots, sans [REL]) ; exemples > 2 048 jetons écartés : 132 010 gardés par époque sur 145 000 (synthétique 21 % écarté).
- **Réglages (§13) :** tout le modèle entraîné ; AdamW (0,9 ; 0,999), 1e-4 tronc, 5e-4 têtes et vecteurs nouveaux, décroissance 0,05 (aucune sur δ), échauffement 500 pas, lot de 32 contextes, abandon 0,1, bf16, norme bornée à 1.
- **Durée :** 5 époques, 20 625 pas, 2 sessions (2026-11-25 23 h 42 → 2026-11-26 15 h 38), 10 tranches de 2 h au plus, **15,8 h de calcul**, ≈ 12 contextes/s (A1 : 1,5 à 1,8). Perte 2,38 → ≈ 0,2 ; aucun incident.
- **Suivi :** `runs/2026-11-25-b-fin/perte.html` (`make courbe-b-fin`), publiée en artefact privé : courbes, tableau A0 / A1 / B, exemples. Copie dans `reports/pages/`.

## Écarts avec SPEC.md
- **Comparaisons non faites (§14, « Comparaisons de la phase 6 ») :** RAG classique en texte libre, ablations sur B-S (sans biais de relations, pivots de noms, biais dépendant de la requête, clause comme unité). Le livrable « tableau de résultats complet » se limite à A0, A1, B-S.
- B-M non entraîné (§9 : seulement si B-S passe ; B-S passe, choix de s'arrêter).
- Exemples > 2 048 jetons BPE comptés faux pour B (A1 : 2 500 jetons SmolLM2).
- Pas de décroissance du pas d'apprentissage après l'échauffement (§13 n'en fixe pas ; comme la phase 4) ; une seule graine.
- Synthèse (tête de langage gardée) non entraînée ni mesurée.

## Risques ouverts
- Une seule graine : un écart de 0,02 de F1 entre modèles est proche du bruit.
- Limite de 2 048 jetons : les dossiers longs ne passent pas dans B sans attention creuse (FlexAttention indisponible sous Windows).
- Les risques de la phase 5 restent : 90 % du corpus anonymisé sans GLiNER, licences des données non vérifiées en ligne.

## Clôture de la phase et du projet
Phase close le 2026-11-26 (demande de Raphael) : `make test-complet` passé (419 passés, 1 ignoré ; T11 : 2 passés), étiquette `phase-6-ok`, fusion dans `main`.

**Le projet s'arrête ici, à la demande de Raphael** : la phase 7 (dégradations, OCR réel, pièces rédigées par LLM) n'est pas faite. Bilan :
- **Phases 1 à 3 :** garanties par construction, sans poids (aucun nom, nombre ou date affiché hors du contexte ; suites de référence toutes acceptées).
- **Phase 4 :** la tâche s'apprend sur un modèle pré-entraîné ; A1 (attention relationnelle) fait mieux que A0.
- **Phase 5 :** un modèle pré-entraîné de zéro sur un corpus anonymisé ; aucune fuite mesurable des canaris naturels, fuite nette des canaris forcés à 100 répétitions.
- **Phase 6 :** ce modèle amnésique, réglé sur la citation, atteint 96,9 % du F1 de A1 au niveau 0 et le dépasse sur HotpotQA.

## Questions pour Raphael
Aucune.
