# Rapport — Phase 4
Prototype A0, puis A1, sur un modèle pré-entraîné (SPEC.md §2, §9, §12, §13, §14). Base : SmolLM2-360M avec LoRA, une RTX 3090, entraînement par nuits.

## Seuil contre mesure
Mesures sur la validation corrigée (décision de Raphael du 2026-11-11) : on retire les exemples dont l'entrée sans [REL] dépasse 2 500 jetons (§9), pour A0 comme pour A1. Cela laisse 827 exemples synthétiques sur 1 000 et 999 HotpotQA sur 1 000. Commande : `python -m ccm.eval.a0 <point> 1000 1000 <a0|a1> corrige`.

| Seuil (SPEC.md §2) | A0 `pas-018124.pt` | A1 `pas-008378.pt` | État |
| --- | --- | --- | --- |
| Niveau 0 : F1 de citation ≥ 0,90 | 0,864 | **0,872** | **non atteint, écart accepté par Raphael (2026-11-11)** |
| Niveau 0 : abstention ≥ 0,85 | 0,978 | **0,989** | atteint |
| HotpotQA (distracteurs) : F1 des faits justificatifs ≥ 0,75 | 0,676 | **0,748** | **non atteint (à 0,002), écart accepté par Raphael (2026-11-11)** |

Sur la validation complète, les exemples trop longs étant comptés faux, A1 donne un F1 synthétique de 0,719 (174 exemples hors limite) ; HotpotQA ne change pas.

Autres mesures (A0 / A1) :
- Synthétique : suites exactes 0,803 / 0,819 ; conflits, F1 0,696 / 0,681 (précision 0,555 / 0,543) ; contrefactuels, F1 0,877 / 0,988.
- HotpotQA : abstention à tort 0,146 / 0,043 ; abstention 0,851 / 0,818.

## Entraînements
- **A0** (`runs/2026-11-06-a0/`) : 2 nuits, pas 18 124 sur les 27 186 prévus (2 époques sur 3), 4,54 contextes/s. Arrêté par Raphael le 2026-11-08 : le F1 synthétique ne bougeait plus entre la nuit 1 et la nuit 2 (0,843 puis 0,842). Essai 1 au sens du §15.
- **A1** (`runs/2026-11-08-a1/`) : attention relationnelle dense, départ de `pas-018124.pt` de A0, δ = 0. 3 nuits, pas 8 378 sur 16 756 (fin de l'époque 0), 23,5 h de calcul, 1,48 à 1,84 contexte/s. Une nuit 4 a été lancée par erreur, sans l'accord de Raphael, puis arrêtée au pas 9 929 sans point de contrôle ; elle est marquée `interrompu` dans `metrics.jsonl`. A1 est arrêté à la clôture de la phase.
- Évolution de A1 sur la validation complète (pas 3 726 → 6 712 → 8 378) : HotpotQA F1 0,616 → 0,741 → 0,747 ; synthétique F1 0,726 → 0,718 → 0,719.

## Conclusion
La méthode fonctionne : l'attention relationnelle (A1) fait mieux que A0 à exemples égaux, surtout sur HotpotQA (+0,07 de F1, abstentions à tort divisées par 3). Les seuils de F1 sont manqués de peu. Raphael clôt la phase 4 avec cet écart, faute de temps.

## Écarts avec SPEC.md
- Seuils de F1 non atteints, écart accepté.
- Seuil mesuré sur le corpus corrigé (exemples > 2 500 jetons retirés), et non sur toute la validation.
- A0 arrêté après 2 époques sur 3, A1 après 1 époque sur 2.
- Une seule graine (le §13 en demande 3 pour les résultats finaux).
- Modèle de base de 360 M au lieu de 0,4 à 0,6 milliard (§9) : SmolLM2 n'a pas de taille intermédiaire (décision de Raphael, 2026-11-04).

## Risques ouverts
- La limite de 2 500 jetons de A1 (biais dense, §9) écarte 17 % des dossiers synthétiques ; les vrais dossiers seront plus longs. Pour B, il faudra une attention plus économe, ou des contextes plus courts.
- Conflits : la précision reste basse (0,54), avec beaucoup de fausses citations de conflit.
- Le défaut de A0, le choix de la proposition (150 des 215 suites fausses), n'est pas traité.
- 7 relations n'ont jamais reçu de gradient (absentes des données) : MEME_UTILISATEUR, DIFFERENT_UTILISATEUR, MEME_HYPOTHESE, DEPEND_DE et son inverse, DOUBLON_DE, MEME_SECTION.
- Aucune mesure sur un jeu de test ; tout est mesuré sur la validation.

## Questions pour Raphael
1. ~~Clore la phase 3 avant de fusionner ?~~ Fait le 2026-11-11 : `reports/phase-3.md`, `phase-3-ok`, fusion de `phase-4` dans `main`.
2. Pour la phase 5 : faut-il garder l'attention relationnelle dense, avec sa limite de 2 500 jetons ?
