"""Corpus de pré-entraînement de B (SPEC.md §12) et canaris (§14).

Étapes (`ccm pretrain <étape>`) : `telecharger`, `brut`, `canaris`, `debit`, `chaine`
(nettoyer, fenêtres, détecter, propager, remplacer, relations, [P], écrire), `bilan`.
Chaque étape écrit `racine/pretrain/<étape>/paquet-NNNNN.parquet` (`.part` puis renommé) et
`etat.json` ; une relance saute les paquets finis.
"""
