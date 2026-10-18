# Rapport — Phase 1
Générateur de monde et corpus synthétique niveau 0, pièces rédigées par gabarits, sans LLM (SPEC.md §2, §12).

## Seuil contre mesure
| Seuil (SPEC.md §2) | Mesure | État |
| --- | --- | --- |
| Livrable : 2 000 dossiers d'entraînement, 200 de validation, 200 de test, avec vérité terrain | `ccm corpus` : 2 000 / 200 / 200 dossiers, 39 231 pièces PDF, `verite.json` et `questions.json` par dossier (79 953 / 8 000 / 7 982 questions) | atteint |
| Le contrôle (noms, nombres, dates de chaque phrase dans ses faits) passe à 100 % | 0 pièce rejetée sur 39 231 ; 0 erreur au contrôle des questions | atteint |
| Même graine, mêmes fichiers | Deux passes complètes : même empreinte SHA-256 de toute l'arborescence (`b4361598…`, 1,45 Go) ; `test_corpus_memes_fichiers` le vérifie à chaque `make test` | atteint |

Autres contrôles : clone neuf de `phase-1` (`f93b7b8`), `make setup && make test` OK (75 tests) ; CI verte sur Ubuntu et Windows.

## Livré
- `worldgen/monde.py` : monde d'un dossier (6 à 20 personnes, 2 à 5 sociétés, 3 à 8 lieux, 15 à 40 événements des 9 types) ; cas durs alias 0,29, même nom de famille 0,18, même nom complet 0,05.
- `worldgen/pieces.py`, `gabarits.yaml` : 8 à 25 pièces de 6 types ; au moins 5 formulations par type d'événement et type de pièce ; les 6 formes d'un nom ; versions contradictoires dans 31 % des dossiers (heure, montant ou personne, dites par deux témoins).
- `worldgen/controle.py` : contrôle de provenance des pièces ; relecture du texte dans le PDF.
- `worldgen/pdf.py` : PDF natif, une pièce par fichier.
- `worldgen/questions.py`, `questions.yaml` : environ 40 questions par dossier des 7 types de §12, vérité terrain par type, synthèse de référence (§10 bis), contrôle.
- `worldgen/wikidata.py` : liste d'exclusion (36 847 noms vérifiés, 5 956 exclus).
- Séparation : graines, réservoirs de noms et gabarits (pièces et questions) propres au test ; `controle.json` → `separation` vide (aucune graine, aucun dossier, aucune chaîne de nom en commun).

| Partie | Dossiers | Graines | Réservoir et gabarits | Conflits (dossiers) | Part des questions de conflit |
| --- | --- | --- | --- | --- | --- |
| entraînement | 2 000 | 0 à 1 999 | entraînement | 623 | 0,087 |
| validation | 200 | 1 000 000 à 1 000 199 | entraînement | 62 | 0,087 |
| test | 200 | 2 000 000 à 2 000 199 | test | 70 | 0,092 |

## Écarts avec SPEC.md
- Questions de conflit : 8,7 % au lieu de 10 % (un seul événement contredit par dossier). Accepté par Raphael le 2026-10-17.
- Liste Wikidata réduite aux libellés et alias français, en correspondance exacte (accord de Raphael, 2026-10-15).
- Surnom en début de ligne : garde sa minuscule (« le Chat a … »), pour que la surface d'un fait reste la forme exacte.
- Nouveau fichier `configs/worldgen.yaml` (absent de la liste de §3).
- La validation garde le réservoir et les gabarits d'entraînement ; §12 demande des gabarits différents pour le test seulement.

## Risques ouverts
- **Licence de PyMuPDF : AGPL.** Décision de Raphael (2026-10-18) : code fermé, poids ouverts. PyMuPDF reste dans `worldgen` (outil interne, jamais distribué ; l'AGPL ne couvre pas les fichiers produits). L'ingestion de la phase 2 utilisera une bibliothèque sans copyleft (pdfplumber ou pypdfium2), et PyMuPDF sortira des dépendances distribuées.
- **COURRIER** n'a pas de motif d'en-tête dans la table de §5 : l'ingestion de la phase 2 classera ces pièces AUTRE (rang 0).
- **Liste V** (phase 5) absente : le contrôle des mots de la synthèse est une liste de mots refusés. Il faudra le refaire contre V.
- **Homonymes Wikidata** sous une autre graphie (sans accent, autre casse) ou seulement en anglais : non vus.
- Gabarits seulement : le corpus est très régulier. Le passage aux vraies pièces se mesure en phase 7.
- `verite.json` contient les noms. Le fichier reste dans `runs/` (hors de git) et ne doit pas servir d'entraînement sans passer par l'anonymiseur.
- Questions de conflit dont les témoins ne sont nommés que par initiales : le conflit ne se lit que par la date.

## Questions pour Raphael
1. ~~PyMuPDF (AGPL)~~ : tranché le 2026-10-18 (voir Risques ouverts).
2. COURRIER : faut-il ajouter un motif d'en-tête à la table de §5 (« Objet : », par exemple) ? Sinon, faut-il laisser ces pièces en AUTRE ?
3. §16 encore ouvert : heures et dépense maximale sur la RTX 3090 ; modèle enseignant 7B exact (bloque la phase 4).
4. Accord pour l'étiquette `phase-1-ok` et la fusion de `phase-1` dans `main` après cette relecture ?
