# Rapport — Phase 5
Pré-entraînement de B : corpus anonymisé, tokenizer, modèle de zéro (SPEC.md §2, §8, §9, §12, §13, §14). B-S, 110 M paramètres, une RTX 3090. Rapport écrit le 2026-11-25.

## Seuil contre mesure
| Seuil (SPEC.md §2) | Mesure | État |
| --- | --- | --- |
| Test T1 exact | `test_t1_permutation_exacte` passe (logits et pertes de pointeur à 1e-5 en float32, δ non nul) ; `make test` du 2026-11-25 : 412 passés, 1 ignoré. | atteint |
| Perte de validation stable | L_pré de validation (1 000 fenêtres), tous les 1 000 pas : 5,81 (pas 1 000) → 4,01 (10 000) → 3,62 (19 000) → **3,34** (29 329). Baisse continue, un seul pic isolé (4,74 au pas 8 000, revenu à 4,03 au pas 9 000). Aucun NaN ; norme du gradient ≈ 0,8 en fin d'entraînement. | atteint |
| Taux d'extraction des canaris naturels mesuré et rapporté | Voir ci-dessous (`runs/2026-11-21-b/canaris.json`, point `pas-029329.pt`). | atteint |

## Canaris (§14)
Faux faits sur des personnes inventées, cachés dans le corpus (« Selon ses proches, X a pour mot fétiche sulfamide »). Mesure : rang de la vraie fin parmi 1 000 fins candidates, tête de langage, mode causal, nom en clair dans le préfixe ; extraction = part des canaris au rang 1 (au hasard : 0,1 %, rang moyen ≈ 500). Chaque phrase est aussi posée avec 5 noms **témoins** (même générateur, jamais vus) : la phrase répétée s'apprend sans le nom, seul l'écart au témoin compte comme **fuite**.

| Canaris | Répétitions | n | Vrai nom | Témoin | Fuite | Rang moyen (vrai / témoin) |
| --- | --- | --- | --- | --- | --- | --- |
| Naturels | 1 | 100 | 0 % | 0 % | 0 | 503 / 502 |
| Naturels | 10 | 100 | 0 % | 0 % | 0 | 339 / 337 |
| Naturels | 100 | 100 | 2,0 % | 2,4 % | **−0,4 pt** | 21 / 21 |
| Forcés | 1 | 100 | 0 % | 0 % | 0 | 449 / 453 |
| Forcés | 10 | 100 | 0 % | 0 % | 0 | 307 / 313 |
| Forcés | 100 | 100 | 10,0 % | 3,0 % | **+7,0 pts** | 17 / 21 |

- **Canaris naturels : aucune fuite mesurable.** Avec le vrai nom, le modèle ne fait pas mieux qu'avec un nom jamais vu, même à 100 répétitions (2,0 % contre 2,4 % ; vrai nom mieux classé qu'un témoin dans 43 % des cas, ≈ hasard).
- **Canaris forcés (nom en clair) : fuite nette à 100 répétitions** (+7 pts ; vrai nom mieux classé que le témoin dans 73 % des cas). La mesure voit donc bien une fuite quand il y en a une : l'anonymisation l'efface.
- À 1 et 10 répétitions, rien n'est retenu, nom en clair ou non.
- La première mesure, sans témoin (`canaris-sans-temoin.json`), donnait 2 % et 10 % ; les 2 % des naturels venaient de la phrase, pas du nom.

## Exemples de génération
`ccm pretrain generer-b` (`generation.json`, 5 débuts fixes, température 0,8, top-p 0,9) : français et anglais grammaticaux, registres reconnus (droit, presse, encyclopédie), sens faible et répétitions ; noms et valeurs remplacés par des slots (⟨PER⟩, ⟨DATE⟩…), parfois au mauvais type (« la région de ⟨PER⟩ »). Textes dans la page.

## Entraînement
- **Corpus** (`final/`, 2026-11-19) : 1 878 978 fenêtres, 2,33 G jetons SmolLM2 (≈ 1,68 G jetons BPE), 72 % fr, 28 % en. GLiNER sur 10 % des documents seulement (règle des 40 h) ; sur ces 10 %, la chaîne sans GLiNER rate PER 14,8 %, ORG 22,6 %, LIEU 8,1 %, AUTRE 5,0 % des zones.
- **BPE** : 32 000 jetons, 19 jetons spéciaux, appris sur 25 % des fenêtres.
- **B-S** (`runs/2026-11-21-b/`) : 1 passage, 29 329 pas de 64 séquences (2 048 jetons au plus), ≈ 1,53 G jetons BPE vus. 7 sessions du 2026-11-21 au 2026-11-25, **50,1 h de calcul** (pas refaits exclus) ; ≈ 9 900 jetons/s.
- **Incidents** : la mémoire du GPU sature après quelques heures (24,3 Go, avertissement OOM de `CUDACachingAllocator`) et le débit tombe jusqu'à 20–87 s/pas (nuit 3, nuit du 23). Correctif : tranches de 2 h (`runs/b-session-lancer.ps1`), chaque reprise repartant d'un point exact ; plus aucun ralentissement ensuite. Une session arrêtée le 24 a fait refaire les pas 20 001 à 21 594 (lignes en double dans `metrics.jsonl`, comptées une fois par `courbe_b`).
- **Suivi** : page `runs/2026-11-21-b/perte.html` (`make courbe-b`), publiée en artefact privé : courbes, sessions, canaris, exemples de génération.

## Écarts avec SPEC.md
- 1 passage au lieu de 2 (§13) ; budget de 40 h dépassé (50,1 h), accepté par Raphael.
- Une seule graine.
- Pas de `torch.compile` ni de FlexAttention (triton absent sous Windows) : attention dense.
- Seuil GLiNER de 40 h au lieu de 3 jours (§12) ; GLiNER sur 10 % du corpus.
- JORF exclu des sources ; canaris forcés en clair dans des fichiers d'entraînement (exigé par §14, noms inventés).
- Fenêtres comptées avec le tokenizer de SmolLM2, coupées à 2 048 jetons BPE (1,6 % des fenêtres).
- Sonde en livre fermé (§14) et modèle témoin non anonymisé : non faits.

## Risques ouverts
- Canaris : 100 par groupe ; un écart de quelques points reste dans le bruit. Aucun canari à 1 000 répétitions.
- 90 % du corpus anonymisé sans GLiNER, avec 15 % de zones PER ratées sur l'échantillon de contrôle.
- 1,53 G jetons pour 110 M paramètres, sous le ratio de Chinchilla (≈ 2,2 G).
- Saturation de la mémoire du GPU pendant l'entraînement, cause non trouvée (contournée par les tranches de 2 h).
- Licences des données non vérifiées en ligne (remises à plus tard).

## Questions pour Raphael
1. Clore la phase 5 maintenant (`make test-complet`, étiquette `phase-5-ok`, fusion dans `main`) ?
2. Second passage de B (≈ 45 h) plus tard, ou passage direct à la phase 6 ?
