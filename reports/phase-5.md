# Rapport — Phase 5
Pré-entraînement de B : corpus anonymisé, tokenizer, modèle de zéro (SPEC.md §2, §8, §9, §12, §13, §14). B-S, 110 M paramètres, une RTX 3090. Rapport écrit le 2026-11-25.

## Seuil contre mesure
| Seuil (SPEC.md §2) | Mesure | État |
| --- | --- | --- |
| Test T1 exact | `test_t1_permutation_exacte` passe (logits et pertes de pointeur à 1e-5 en float32, δ non nul) ; `make test` du 2026-11-25 : 411 passés, 1 ignoré. | atteint |
| Perte de validation stable | L_pré de validation (1 000 fenêtres), tous les 1 000 pas : 5,81 (pas 1 000) → 4,01 (10 000) → 3,62 (19 000) → **3,34** (29 329). Baisse continue, un seul pic isolé (4,74 au pas 8 000, revenu à 4,03 au pas 9 000). Aucun NaN ; norme du gradient ≈ 0,8 en fin d'entraînement. | atteint |
| Taux d'extraction des canaris naturels mesuré et rapporté | Voir ci-dessous (`runs/2026-11-21-b/canaris.json`, point `pas-029329.pt`). | atteint |

## Canaris (§14)
Rang de la vraie fin parmi 1 000 fins candidates, tête de langage, mode causal, nom en clair dans le préfixe. Au hasard : extraction 0,1 %, rang moyen ≈ 500.

| Canaris | Répétitions | n | Extraction | Rang moyen |
| --- | --- | --- | --- | --- |
| Naturels | 1 | 100 | 0 % | 502,7 |
| Naturels | 10 | 100 | 0 % | 339,3 |
| Naturels | 100 | 100 | **2 %** | 21,2 |
| Forcés | 1 | 100 | 0 % | 448,9 |
| Forcés | 10 | 100 | 0 % | 306,9 |
| Forcés | 100 | 100 | **10 %** | 16,6 |

- À 1 répétition, rien n'est retenu, nom anonymisé ou non.
- À 100 répétitions, un nom laissé en clair (forcés) est extrait 5 fois plus souvent qu'un nom passé par la chaîne (naturels) : 10 % contre 2 %.
- Le rang moyen baisse autant pour les naturels que pour les forcés (21 contre 17 à 100 répétitions) : le modèle apprend la phrase du canari (« le plus beau mot est … ») avec sa fin, même sans le nom. Le rang mesure donc surtout la phrase, pas le lien entre le nom et le fait (voir les risques).
- Canaris naturels au rang 1 : `naturel-220`, `naturel-279`. Leur nom a peut-être échappé à la détection ; à vérifier dans `final/`.

## Entraînement
- **Corpus** (`final/`, 2026-11-19) : 1 878 978 fenêtres, 2,33 G jetons SmolLM2 (≈ 1,68 G jetons BPE), 72 % fr, 28 % en. GLiNER sur 10 % des documents seulement (règle des 40 h) ; sur ces 10 %, la chaîne sans GLiNER rate PER 14,8 %, ORG 22,6 %, LIEU 8,1 %, AUTRE 5,0 % des zones.
- **BPE** : 32 000 jetons, 19 jetons spéciaux, appris sur 25 % des fenêtres.
- **B-S** (`runs/2026-11-21-b/`) : 1 passage, 29 329 pas de 64 séquences (2 048 jetons au plus), ≈ 1,53 G jetons BPE vus. 7 sessions du 2026-11-21 au 2026-11-25, **50,1 h de calcul** (pas refaits exclus) ; ≈ 9 900 jetons/s.
- **Incidents** : la mémoire du GPU sature après quelques heures (24,3 Go, avertissement OOM de `CUDACachingAllocator`) et le débit tombe jusqu'à 20–87 s/pas (nuit 3, nuit du 23). Correctif : tranches de 2 h (`runs/b-session-lancer.ps1`), chaque reprise repartant d'un point exact ; plus aucun ralentissement ensuite. Une session arrêtée le 24 a fait refaire les pas 20 001 à 21 594 (lignes en double dans `metrics.jsonl`, comptées une fois par `courbe_b`).
- **Suivi** : page `runs/2026-11-21-b/perte.html` (`make courbe-b`), publiée en artefact privé : courbes, sessions, tableau des canaris.

## Écarts avec SPEC.md
- 1 passage au lieu de 2 (§13) ; budget de 40 h dépassé (50,1 h), accepté par Raphael.
- Une seule graine.
- Pas de `torch.compile` ni de FlexAttention (triton absent sous Windows) : attention dense.
- Seuil GLiNER de 40 h au lieu de 3 jours (§12) ; GLiNER sur 10 % du corpus.
- JORF exclu des sources ; canaris forcés en clair dans des fichiers d'entraînement (exigé par §14, noms inventés).
- Fenêtres comptées avec le tokenizer de SmolLM2, coupées à 2 048 jetons BPE (1,6 % des fenêtres).
- Sonde en livre fermé (§14) et modèle témoin non anonymisé : non faits.

## Risques ouverts
- **Mesure des canaris trop faible pour isoler le nom.** Sans un préfixe témoin (même phrase, autre nom inventé), on ne sait pas si le rang vient du nom ou de la phrase seule. Mesure peu coûteuse à ajouter (minutes de GPU).
- 90 % du corpus anonymisé sans GLiNER, avec 15 % de zones PER ratées sur l'échantillon de contrôle.
- 1,53 G jetons pour 110 M paramètres, sous le ratio de Chinchilla (≈ 2,2 G).
- Saturation de la mémoire du GPU pendant l'entraînement, cause non trouvée (contournée par les tranches de 2 h).
- Licences des données non vérifiées en ligne (remises à plus tard).

## Questions pour Raphael
1. Ajouter le préfixe témoin aux canaris (même phrase, autre nom) avant de clore la phase ?
2. Clore la phase 5 maintenant (`make test-complet`, étiquette `phase-5-ok`, fusion dans `main`) ?
3. Second passage de B (≈ 45 h) plus tard, ou passage direct à la phase 6 ?
