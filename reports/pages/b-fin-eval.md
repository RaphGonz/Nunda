# Mesures de B : 2026-11-25-b-fin/pas-020625.pt (pas 20625) — corpus corrigé (exemples de A1 > 2 500 jetons SmolLM2 retirés)

## Seuils de la phase 4 (validation)

| Source | Mesure | Seuil | Mesure | Passe |
| --- | --- | --- | --- | --- |
| synthetique | f1 | 0.90 | 0.845 | non |
| synthetique | abstention | 0.85 | 0.950 | oui |
| hotpot | f1 | 0.75 | 0.769 | oui |

## Par source et par genre

| Source | Genre | n | P | R | F1 | exactes | abstention | abst. à tort |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetique | total | 827 | 0.838 | 0.860 | 0.845 | 0.827 | 0.950 | 0.000 |
| synthetique | contrefactuel | 27 | 0.907 | 0.907 | 0.907 | 0.889 | – | 0.000 |
| synthetique | dans_limite | 787 | 0.883 | 0.906 | 0.891 | 0.869 | 0.989 | 0.000 |
| synthetique | normal | 675 | 0.851 | 0.851 | 0.851 | 0.815 | 0.978 | 0.000 |
| synthetique | abstention | 90 | – | – | – | 0.922 | 0.922 | – |
| synthetique | conflit | 35 | 0.557 | 0.957 | 0.700 | 0.771 | – | 0.000 |
| hotpot | total | 999 | 0.814 | 0.749 | 0.769 | 0.506 | 0.860 | 0.024 |
| hotpot | normal | 852 | 0.814 | 0.749 | 0.769 | 0.455 | – | 0.025 |
| hotpot | dans_limite | 993 | 0.820 | 0.754 | 0.775 | 0.509 | 0.860 | 0.024 |
| hotpot | abstention | 118 | – | – | – | 0.864 | 0.864 | – |
| hotpot | contrefactuel | 26 | 0.808 | 0.747 | 0.771 | 0.500 | – | 0.000 |
| hotpot | abstention_contexte | 3 | – | – | – | 0.667 | 0.667 | – |

Décodage : 533 s pour 1826 exemples.
Hors limite (arrêtés à 2048 jetons, faux dans « total ») : 46.
