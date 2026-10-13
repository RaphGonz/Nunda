# Spécification d'implémentation

Oct 2, 2026 · @Raphael

Cet onglet dit à un agent comment programmer et entraîner le CCM, phase par phase, sans autre source. Il précise l'onglet de synthèse. Quand les deux diffèrent, cet onglet fait foi pour l'implémentation.

## 1. Corrections par rapport à la synthèse

La relecture a trouvé 14 points faux, contradictoires ou trop vagues pour être programmés. Chaque ligne donne la décision retenue. Les sections suivantes appliquent ces décisions.

| N° | Point | Problème dans la synthèse | Décision |
| --- | --- | --- | --- |
| C1 | Pivots de noms | Le texte dit que le pivot est la cible du pointeur. La grammaire dit que le pointeur vise une mention. Un jeton « sans position » n'est pas défini avec RoPE. | Aucun pivot en v1. Le pointeur vise les mentions. Le code additionne les probabilités des mentions du même nom. Le pivot devient une ablation de la phase 6. |
| C2 | Test d'équivariance | « Deux renommages donnent les mêmes logits ». En variante B, le modèle ne reçoit aucun nom : ce test est toujours vrai et ne trouve aucune fuite. | Trois tests séparés : permutation des indices (modèle), anonymiseur avec mentions de référence (code), bout en bout (mesure, pas garantie). Voir section 14. |
| C3 | Portée de l'équivariance | La garantie est écrite pour le système. Le détecteur de noms et BM25 changent quand les noms changent. | La garantie vaut pour le modèle, à contexte anonymisé égal. L'effet d'un renommage sur le système entier est une mesure publiée. |
| C4 | Règle d'identité du vérificateur | Le code doit savoir qu'une citation « désigne la personne de la question sous un autre nom ». Or le code ne décide jamais de l'identité. | Règle d'ancrage par noms identiques, calculable par le code. Voir section 11. |
| C5 | Clé d'obligation | « Une étape d'extraction » non définie. Elle contredit « aucun LLM génératif hors du modèle ». | Signature de texte masqué, calculée par le code. Les conflits reformulés ne sont pas détectés en v1 : limite écrite. Voir section 5. |
| C6 | Pré-entraînement | L'objectif décrit est causal. Le tronc cible est un prefix-LM bidirectionnel sur l'entrée. Les deux ne vont pas ensemble. | Objectif mixte : une partie des séquences en causal, une partie avec préfixe bidirectionnel masqué. Voir section 13. |
| C7 | Langue | HotpotQA et TAB sont en anglais. FQuAD et PIAF sont en français. La langue du pré-entraînement n'est pas dite. | Tokenizer et pré-entraînement bilingues, 70 % français et 30 % anglais. Le produit reste en français. |
| C8 | Relations | Il manque DIFFÉRENT (utilisateur) et MÊME_PIÈCE dans l'attention. Les relations orientées n'ont qu'un sens. La détection n'a pas de type pour un nom inconnu. | Liste fermée de 24 relations, section 6. Deux identifiants pour chaque relation orientée. Nouveau type AUTRE. |
| C9 | Prototype | La variante A demande de modifier l'attention de Qwen dès le début. | A0 : relations écrites en jetons dans un en-tête, aucun changement d'attention. A1 : biais d'attention ajoutés, à zéro au départ. A0 teste toute la chaîne en premier. |
| C10 | Pointeur | Décision ouverte : jetons de proposition, puis tête sur les positions. | Tête sur les positions dès A0. Même code en A et en B, aucune limite de propositions. |
| C11 | Point de départ KLLM | La synthèse compte sur les modèles KLLM. L'[article](https://arxiv.org/abs/2607.12831) annonce une publication des modèles, sans date. | Le prototype part d'un petit modèle ouvert (Qwen ou SmolLM). L'agent n'attend pas KLLM. |
| C12 | Softmax unique | Les logits du lexique et les scores de pointeur n'ont pas la même échelle. | Une température et un biais appris par famille de sortie. |
| C13 | Slots masqués | Un slot masqué garde ses relations : la relation « même chaîne » donne la réponse. | Un slot masqué ou à prédire perd toutes ses relations de noms. |
| C14 | Connecteurs | La règle de conception cite « selon ». La grammaire ne l'a pas. | La grammaire fait foi : cinq connecteurs. « selon » est retiré. |

**Trois précisions de plus.** Une proposition de plus de 128 jetons est coupée, avec un lien DÉPEND_DE entre ses parties. CALCUL n'accepte aucune constante écrite par le modèle et aucun comptage. Le modèle ne lit jamais d'étiquette comme « PER4 » en variante B : ces étiquettes existent seulement dans le code et dans les exemples du document.

## 2. Ordre de construction

Le projet se construit en 8 phases. Les phases 0 à 3 sont du code sans GPU : elles produisent toute la chaîne autour du modèle et se testent avec un « modèle oracle » qui rejoue les actions de référence. Une phase commence seulement quand la phase précédente passe son seuil.

| Phase | Contenu | Livrable | Seuil de passage |
| --- | --- | --- | --- |
| 0 | Dépôt, configuration, CI, schémas de données | Dépôt qui s'installe avec une commande ; CI verte | `make test` passe sur une machine neuve |
| 1 | Générateur de monde et corpus synthétique niveau 0, pièces rédigées par gabarits (sans LLM) | 2 000 dossiers d'entraînement, 200 de validation, 200 de test, avec vérité terrain | Le contrôle (noms, nombres, dates de chaque phrase dans ses faits) passe à 100 % ; même graine, mêmes fichiers |
| 2 | Ingestion, graphe, anonymiseur, recherche | Commandes `ingest`, `search`, `anonymize` | Sur le niveau 0 : rappel des noms PER ≥ 0,98 ; rappel des propositions justificatives dans le budget ≥ 0,95 ; test T2 exact |
| 3 | Grammaire, automate, vérificateur, rendu, modèle oracle | Commande `answer --oracle` de bout en bout | 100 % des suites de référence acceptées par l'automate ; 100 000 décodages aléatoires sous masque, tous valides ; aucun nom, nombre ou date affiché hors du contexte |
| 4 | Prototype A0, puis A1, sur un modèle pré-entraîné | Points de contrôle A0 et A1, rapport de mesures | A0 sur le niveau 0 : F1 de citation ≥ 0,90, abstention ≥ 0,85 ; HotpotQA (distracteurs) : F1 des faits justificatifs ≥ 0,75 |
| 5 | Pré-entraînement de B : corpus anonymisé, tokenizer, modèle de zéro | Point de contrôle B pré-entraîné, taux de canaris | Test T1 exact ; perte de validation stable ; taux d'extraction des canaris naturels mesuré et rapporté |
| 6 | Réglage fin de B ; comparaison A0, A1, B et RAG classique ; ablations | Tableau de résultats complet | B atteint au moins 95 % du F1 de citation de A1 sur le niveau 0 ; sinon, rapport des causes |
| 7 | Niveaux de dégradation 1 à 5, OCR réel, pièces rédigées par LLM | Courbes par niveau, rapport final | Mesures publiées pour chaque niveau ; pas de seuil : c'est le résultat de l'article |

Les seuils sont des valeurs de départ. Si un seuil n'est pas atteint après trois essais documentés, l'agent s'arrête et rapporte (section 15).

**Ce que chaque phase prouve.** Les phases 1 à 3 prouvent les garanties par construction, sans aucun poids. La phase 4 prouve que la tâche s'apprend. Les phases 5 et 6 prouvent la contribution : l'amnésie et l'équivariance exacte. La phase 7 mesure la robustesse.

## 3. Pile technique et dépôt

Tout le projet est en Python, dans un seul dépôt, et tourne hors ligne après le téléchargement des modèles et des jeux de données.

| Besoin | Choix par défaut | Remarque |
| --- | --- | --- |
| Langage, environnement | Python 3.11 ou plus, `uv` | Versions figées dans `uv.lock` |
| Réseau de neurones | PyTorch 2.5 ou plus, `transformers`, `peft`, `tokenizers`, `safetensors` | PyTorch 2.5 est le minimum pour FlexAttention |
| Stock et graphe | SQLite (bibliothèque standard) | Un fichier par base de dossiers |
| Exemples d'entraînement | Parquet (`pyarrow`), un fichier par lot de 10 000 exemples |  |
| PDF natif | PyMuPDF | Texte et position de chaque mot |
| OCR | Tesseract 5, modèle `fra` | Donne une confiance par mot. Option : docTR |
| Phrases | Découpeur à règles (`pysbd`, français) et liste d'abréviations juridiques | Option pour les niveaux 2 et plus : `wtpsplit` |
| Détection de noms | Union de GLiNER multilingue, spaCy `fr_core_news_lg` et règles | Modèles encodeurs, non génératifs. Vérifier chaque licence au téléchargement |
| BM25 | `bm25s`, racinisation Snowball français (`PyStemmer`) |  |
| Quasi-doublons | `datasketch` (MinHash) |  |
| Distance de chaînes | `rapidfuzz` |  |
| Calcul exact | `decimal` (bibliothèque standard) | Jamais de flottant pour un CALCUL |
| Configuration, commandes | YAML, `pydantic`, `typer` | Aucun paramètre écrit en dur dans le code |
| Tests | `pytest`, `hypothesis` (tests de propriétés), `ruff` |  |
| Suivi | Fichiers JSONL et TensorBoard, en local | Aucun service en ligne par défaut |

```text
ccm/
  pyproject.toml   Makefile   README.md   JOURNAL.md
  configs/           ingest.yaml  search.yaml  model_a0.yaml  model_a1.yaml
                     model_b_s.yaml  model_b_m.yaml  pretrain.yaml  finetune.yaml
  ccm/
    schema.py        contrats de données (section 4), source unique
    ingest/          extract  piece_type  segment  tables  numbers  dedup  conflicts  tree
    ner/             detectors  union  propagate
    graph/           store (SQLite)  edges
    search/          bm25  expand  retrieve
    anonymize/       names  relations  units  table  encode
    grammar/         lexicon  automaton  mask
    model/           config  attention (référence + flex)  trunk  heads  ccm_a  ccm_b  decode
    verify/          verifier  render  trace
    data/            worldgen/  hotpot  squad_fr  finqa  legi  negatives  pretrain_corpus  canaries
    train/           pretrain  finetune  losses
    eval/            metrics  equivariance  amnesia  report
    cli.py
  tests/             unit/  property/  golden/ (petits dossiers figés avec sorties attendues)
  runs/              sorties des entraînements ; hors de git
```

**Règles de code.**

- `schema.py` définit chaque structure une seule fois. Les autres modules importent ces classes.
- Chaque fonction aléatoire reçoit une graine. La même graine donne les mêmes fichiers, octet pour octet.
- Les modules `grammar`, `verify` et `anonymize` portent les garanties. Écrire leurs tests avant leur code.
- Aucun appel réseau dans `ingest`, `search`, `anonymize`, `model`, `verify`. Un test le contrôle.
- Le code de l'inférence et le code de préparation des données d'entraînement appellent les mêmes fonctions d'anonymisation et de masque. Aucune copie.

## 4. Contrats de données

Deux structures portent tout le projet : le stock (SQLite), qui garde le texte original avec les noms, et l'exemple de modèle (JSON), qui ne contient aucun nom. La frontière entre les deux est l'anonymiseur.

### Stock et graphe (SQLite)

```sql
CREATE TABLE piece (
  piece_id TEXT PRIMARY KEY, chemin TEXT, sha256 TEXT, type TEXT,   -- PV_AUDITION, PV_CONSTATATION, RAPPORT,
  rang INTEGER, nb_pages INTEGER, revision INTEGER);                -- COURRIER, CONTRAT, RELEVE, LOI, AUTRE
CREATE TABLE proposition (
  prop_id INTEGER PRIMARY KEY, piece_id TEXT, page INTEGER, ordre INTEGER,
  texte TEXT,                 -- texte extrait, jamais modifié
  genre TEXT,                 -- PHRASE, LIGNE_TABLEAU, CHAMP, EN_TETE, PARTIE
  ocr_conf REAL,              -- 1.0 pour un PDF natif
  signature TEXT,             -- signature de texte masqué (section 5)
  groupe_doublon INTEGER);
CREATE TABLE mention (
  mention_id INTEGER PRIMARY KEY, prop_id INTEGER, debut INTEGER, fin INTEGER,   -- positions en caractères
  surface TEXT, norme TEXT, type TEXT,         -- PER, ORG, LIEU, REF, AUTRE
  detecteurs TEXT);                            -- qui l'a trouvée : gliner, spacy, regle, propagation
CREATE TABLE nombre (
  nombre_id INTEGER PRIMARY KEY, prop_id INTEGER, debut INTEGER, fin INTEGER, surface TEXT,
  genre TEXT,                 -- NUM ou DATE
  valeur TEXT,                -- décimal exact, ou date ISO
  unite TEXT, precision_date TEXT);            -- JOUR, MOIS, ANNEE
CREATE TABLE arete (
  src INTEGER, dst INTEGER, type TEXT,         -- SUIVANTE, DEPEND_DE, CONFLIT, DOUBLON_DE, SECTION_DE
  PRIMARY KEY (src, dst, type));
CREATE TABLE contrainte (
  conv_id TEXT, genre TEXT,                    -- MEME, DIFFERENT, IGNORER_SOURCE
  a_norme TEXT, b_norme TEXT, piece_id TEXT, auteur TEXT, date TEXT);
CREATE TABLE trace (
  reponse_id TEXT PRIMARY KEY, conv_id TEXT, question TEXT, prop_ids TEXT, chemin_recherche TEXT,
  contraintes TEXT, actions TEXT, revision_base INTEGER, modele TEXT, date TEXT);
```

Les nœuds « nom » et « date » du graphe sont des vues : `SELECT DISTINCT norme, type FROM mention` et `SELECT DISTINCT valeur FROM nombre WHERE genre = 'DATE'`. La table `piece.revision` augmente à chaque ajout ou suppression ; la trace l'enregistre.

### Exemple de modèle (JSON)

L'anonymiseur produit cette structure à l'inférence. Les fichiers d'entraînement ont le même format. Le texte contient un marqueur à la place de chaque nom et de chaque nombre. Aucune chaîne de nom n'est dans le fichier.

```json
{
  "id": "syn-000123-q07", "origine": "synthetique", "langue": "fr",
  "question": {"texte": "Avec qui ⟦0⟧ a-t-il signé le contrat ?",
               "marques": [{"genre": "NOM", "type": "PER", "nom": 3}]},
  "historique": [],
  "propositions": [
    {"local": 0, "prop_id": 8812, "piece": 2, "type_piece": "PV_AUDITION", "rang": 1,
     "ocr_bas": false, "citee_avant": false,
     "texte": "⟦0⟧, dit ⟦1⟧, a signé le contrat avec ⟦2⟧ le ⟦3⟧.",
     "marques": [{"genre": "NOM", "type": "PER", "nom": 5},
                 {"genre": "NOM", "type": "PER", "nom": 3},
                 {"genre": "NOM", "type": "ORG", "nom": 9},
                 {"genre": "DATE", "unite": "date", "grandeur": null, "rang_valeur": 4, "valeur_id": 12}]}
  ],
  "relations_noms": [[3, 5, "INITIALES_DE"], [3, 5, "ALIAS_DECLARE"]],
  "relations_props": [[0, 1, "SUIVANTE"]],
  "cible": ["P:0", "SAME", "M:q.0", "M:0.0", "P:0", "FIN"],
  "justificatives": [0]
}
```

- `nom` est un indice local à l'exemple. Le code le tire au hasard à chaque exemple d'entraînement. À l'inférence, il vient de la table de la conversation.
- `valeur_id` est égal pour deux nombres de même valeur et de même unité. La valeur elle-même reste dans le stock.
- Dans `cible`, `P:k` pointe vers la proposition locale k, `M:k.j` vers la marque j de la proposition k (`q` pour la question, `h1` pour le message précédent), `N:k.j` vers un nombre. Les autres éléments sont des jetons du lexique (section 10).

## 5. Ingestion

L'ingestion est une suite de 9 étapes de code, sans modèle génératif. Chaque paramètre ci-dessous est une valeur de départ, écrite dans `configs/ingest.yaml`.

| Étape | Algorithme | Paramètres de départ |
| --- | --- | --- |
| 1. Extraction | PyMuPDF, mot par mot, ordre de lecture par blocs (haut vers bas, colonnes détectées par groupes d'abscisses). Une page sans texte natif passe à l'OCR. Le code recolle les lignes et les mots coupés en fin de ligne ; il ne change rien d'autre. | OCR si la page a moins de 20 caractères natifs ; 300 dpi ; `ocr_conf` = moyenne des confiances des mots ; `ocr_bas` si < 0,85 |
| 2. Pièces et types | Un fichier est une pièce. Dans un fichier, une nouvelle pièce commence à chaque page dont les 15 premières lignes contiennent un motif d'en-tête. Le type vient d'une table de motifs ; le rang vient d'une table type → rang. | Motifs : « PROCÈS-VERBAL », « P.V. n° », « RAPPORT », « RÉQUISITION », « CONTRAT », « RELEVÉ DE COMPTE », « Article L. ». Rang : loi et règlement 1, circulaire 2, doctrine 3, pédagogique 4, autre 0 (non classé) |
| 3. Segmentation | Une proposition par phrase. Une phrase reçoit DÉPEND_DE vers la précédente si elle commence par un mot de la liste, si elle a moins de 4 mots, ou si elle est une réponse dans un motif question-réponse d'audition. | Liste : Toutefois, Cependant, Dans ce cas, En effet, Ainsi, Par conséquent, Il, Elle, Ils, Elles, Celui-ci, Celle-ci, Ce dernier, Cette dernière |
| 3 bis. Phrases longues | Une phrase trop longue est coupée aux points-virgules et aux deux-points. Les parties ont le genre PARTIE et dépendent les unes des autres : citer une partie affiche la phrase entière. | Limite : 128 jetons du tokenizer du modèle (80 mots avant que le tokenizer existe) |
| 4. Tableaux et formulaires | `find_tables()` de PyMuPDF. Une ligne devient une proposition « cellule \| cellule \| … », avec DÉPEND_DE vers la ligne d'en-tête. Une ligne « Libellé : valeur » devient une proposition CHAMP. | Motif de champ : libellé de 2 à 40 caractères avant « : » |
| 5. Noms | Voir section 6. |  |
| 6. Nombres et dates | Expressions régulières pour les formats français. Les références (articles, numéros de PV, téléphones, IBAN, plaques) sont détectées avant et ne sont jamais des nombres. Un nombre en lettres est un slot seulement devant une unité connue. | Unités : €, %, km, m, kg, g, an, mois, jour, heure, minute, heure du jour. Une année seule (1900 à 2100) est une date de précision ANNEE |
| 7. Doublons | Hachage SHA-1 du texte normalisé pour les copies exactes. MinHash sur des triplets de mots pour les quasi-copies. La copie de meilleure confiance OCR est la version gardée ; la recherche ignore les autres ; le rendu les liste (« aussi dans la pièce X, page Y »). | 128 permutations ; seuil de Jaccard 0,9 |
| 8. Conflits | Voir ci-dessous. |  |
| 9. Arbre | Seulement pour les codes en XML de Légifrance. Non requis avant la phase 7. |  |

### Détection des conflits (remplace la « clé d'obligation »)

Deux propositions sont en conflit quand elles disent la même chose avec une valeur différente. Le code le détecte sans comprendre le texte.

1. **Signature.** Remplacer chaque nom par son type, chaque nombre par `NUM:unité`, chaque date par `DATE`. Raciniser les mots, retirer les mots vides. La signature est l'ensemble des racines.
2. **Candidats.** Garder les paires dont les signatures ont un Jaccard ≥ 0,6 (recherche par MinHash LSH), qui ne sont pas des doublons, et dont les noms normalisés de l'une sont inclus dans ceux de l'autre.
3. **Comparaison.** Aligner les nombres et les dates des deux propositions par unité et par ordre. Si une paire alignée a deux valeurs différentes, créer l'arête CONFLIT. Si toutes les valeurs sont égales, ne rien créer.
4. **Négation.** Si le Jaccard est ≥ 0,8 et qu'une seule des deux propositions contient une marque de négation (ne … pas, n', aucun, jamais, non), créer l'arête CONFLIT.

**Limite écrite.** Deux sources qui se contredisent avec des mots très différents ne sont pas détectées en v1. C'est le cas de l'entretien du juriste n° 1 (livre blanc contre Code). Deux pistes pour plus tard, à mesurer sur le rappel : un encodeur de phrases non génératif pour proposer des candidats, ou une action « conflit supposé » du modèle, affichée comme hypothèse. Le corpus synthétique contient des versions contradictoires avec vérité terrain : il mesure la précision et le rappel de cette étape. Cible de précision : 0,9.

### Suppression d'une personne

La commande `ccm forget` reçoit une liste de noms normalisés. Elle caviarde les mentions dans `proposition.texte`, supprime les lignes de `mention`, reconstruit l'index BM25 et augmente la révision. La base est ouverte avec `PRAGMA secure_delete = ON`, puis la commande lance `VACUUM` : sans cela, SQLite garde le texte effacé dans ses pages libres. Test : après la commande, une recherche de la chaîne dans l'index, dans la base et dans le fichier brut de la base ne trouve rien.

## 6. Anonymiseur

L'anonymiseur fait trois choses, toujours avec le même code à l'entraînement et à l'inférence : il détecte les noms, il les remplace par des slots, et il décrit les relations entre les chaînes. Il ne décide jamais qu'un nom désigne une personne donnée.

### Détection : union de quatre détecteurs

| Détecteur | Ce qu'il trouve | Réglage |
| --- | --- | --- |
| D1 : GLiNER multilingue | Personnes, organisations, lieux, adresses, produits | Seuil bas (0,3) : préférer les faux positifs |
| D2 : spaCy `fr_core_news_lg` | PER, ORG, LOC, MISC | Tel quel |
| D3 : règles | REF : articles de code (« L. 2112-2 », « art. 1240 »), numéros de PV et de dossier, téléphone, courriel, IBAN, plaque, SIREN, URL | Expressions régulières dans `configs/ingest.yaml` |
| D4 : majuscules | Tout mot à majuscule initiale, ou tout en majuscules, absent d'un lexique de mots courants. Type AUTRE si aucun autre détecteur ne le type | Lexique : formes courantes du français et de l'anglais |

- **Union.** Deux zones qui se chevauchent fusionnent en la zone la plus longue. Priorité des types : REF, PER, ORG, LIEU, AUTRE.
- **Limites d'un nom.** La zone contient les particules (de, du, de la, van, von, le) et les prénoms composés. Les titres (M., Mme, Me, Dr, Maître, grades) restent du texte, hors du slot.
- **Propagation.** Une chaîne détectée une fois dans une base est masquée partout dans cette base. Pour le corpus de pré-entraînement : partout dans le document ; et partout dans le corpus si elle est détectée dans au moins 30 % de ses occurrences.
- **Messages de l'utilisateur.** Même détection, plus une recherche sans casse de tous les noms déjà connus de la base : l'utilisateur écrit souvent « dupont ».
- **Mesure.** Rappel par type sur le corpus synthétique (mentions connues), sur WikiNER français et sur TAB. Le rappel de KLLM (environ 0,87) est le point de comparaison.

### Normalisation et analyse d'un nom

La norme d'un nom est : NFKC, minuscules, sans accents, tirets et espaces réduits à une espace, titres retirés. Deux mentions de même norme et de même type sont le même nom et reçoivent le même indice.

Pour un nom PER, le code sépare prénoms et nom de famille : un mot tout en majuscules est le nom de famille (« DUPONT Jean-Pierre ») ; sinon le dernier mot, avec ses particules, est le nom de famille. Un mot seul en minuscules a un rôle inconnu. Une chaîne de 1 à 3 majuscules, avec ou sans points (« JP », « J.-P. »), est un jeu d'initiales.

### Les 24 relations

Le modèle reçoit ces relations, et aucune autre. Chaque relation orientée a deux identifiants, un par sens. Les relations 1 à 14 relient des mentions ; 15 relie des nombres ; 16 à 24 relient tous les jetons de deux propositions.

| N° | Relation | Règle exacte (le code) |
| --- | --- | --- |
| 1 | MEME_CHAINE | Même norme et même type |
| 2 | MEME_FAMILLE | Deux noms PER, même nom de famille, normes différentes |
| 3, 4 | INITIALES_DE et son inverse | a est un jeu d'initiales ; il est égal aux initiales des prénoms de b, ou des prénoms et du nom |
| 5 | PROCHE | Distance de Damerau-Levenshtein entre les normes : 1 si la longueur est ≥ 5, jusqu'à 2 si elle est ≥ 10 |
| 6 | INCOMPATIBLE | Même nom de famille et prénoms incompatibles (ni égaux, ni initiale, ni préfixe) ; ou titres de genre différent (« M. » et « Mme ») |
| 7, 8 | SIGLE_DE et son inverse | a a de 2 à 8 majuscules, égales aux initiales des mots pleins de b |
| 9, 10 | INCLUS_DANS et son inverse | Les mots de a sont un sous-ensemble strict des mots de b (« Alpha » et « société Alpha ») |
| 11 | ALIAS_DECLARE | Les deux noms sont dans la même proposition, reliés par un motif : « A, dit B », « A alias B », « A, surnommé B », « A (ci-après B) », « A épouse B », « A, né B » |
| 12 | MEME_UTILISATEUR | Contrainte MEME enregistrée dans la conversation |
| 13 | DIFFERENT_UTILISATEUR | Contrainte DIFFERENT enregistrée dans la conversation |
| 14 | MEME_HYPOTHESE | Hypothèse SAME émise par le modèle à un tour précédent, non refusée par l'utilisateur |
| 15 | MEME_NOMBRE | Même valeur et même unité |
| 16 | MEME_PROPOSITION | Deux jetons de la même proposition |
| 17, 18 | SUIVANTE et son inverse | Propositions voisines dans la même pièce |
| 19, 20 | DEPEND_DE et son inverse | Arête DEPEND_DE du graphe |
| 21 | CONFLIT | Arête CONFLIT du graphe |
| 22 | DOUBLON_DE | Arête DOUBLON_DE du graphe |
| 23 | MEME_PIECE | Deux propositions de la même pièce |
| 24 | MEME_SECTION | Deux propositions du même nœud d'arbre, si un arbre existe |

La relation 11 lit un motif de texte ; elle ne décide rien. Le modèle garde la décision et cite la proposition comme preuve dans SAME(a, b, p).

### Slots et attributs

- **Types de slots.** ⟨PER⟩, ⟨ORG⟩, ⟨LIEU⟩, ⟨REF⟩, ⟨AUTRE⟩, ⟨NUM⟩, ⟨DATE⟩. Une mention devient un seul jeton, quelle que soit sa longueur.
- **Variantes A0 et A1.** Chaque nom distinct reçoit un indice tiré au hasard, sans remise, dans un réservoir de K = 256 vecteurs par type. Le tirage est refait à chaque exemple d'entraînement, et une fois par conversation à l'inférence. Si un contexte a plus de K noms d'un type, la recherche retire ses propositions les moins bien classées.
- **Variante B.** Un seul vecteur par type. L'identité passe seulement par les relations.
- **Nombres.** L'entrée d'un ⟨NUM⟩ est la somme de quatre vecteurs appris : unité (16 unités et « autre »), ordre de grandeur (partie entière de log10 de la valeur absolue, borné de −3 à 12, plus une case pour zéro), rang parmi les valeurs de même unité dans le contexte (rang dense, borné à 63), signe.
- **Dates.** L'entrée d'une ⟨DATE⟩ est la somme de deux vecteurs : précision (JOUR, MOIS, ANNEE) et rang chronologique. Aucun ordre de grandeur : il donnerait l'année.
- **Table de la conversation.** Le dictionnaire norme → indice reste dans le processus de l'anonymiseur. Il n'entre ni dans le modèle, ni dans la trace.

## 7. Recherche

La recherche rend au plus 150 propositions et 3 500 jetons, dans un ordre fixe, avec la raison de chaque choix. Elle utilise deux index : BM25 sur le texte des propositions, et un index inversé norme de nom → propositions.

| Étape | Règle | Valeur de départ |
| --- | --- | --- |
| Index BM25 | Minuscules, sans accents, racines Snowball, mots vides retirés. Les doublons non gardés sont hors de l'index. | k1 = 1,5 ; b = 0,75 |
| 1. Départs par noms | Propositions qui contiennent un nom de la question : norme égale, puis noms reliés par MEME_FAMILLE, INITIALES_DE, INCLUS_DANS, PROCHE ou SIGLE_DE | Au plus 40 propositions par nom, classées par BM25 |
| 1 bis. Départs par texte | Meilleures propositions BM25 pour la question | 30 |
| 2. Extension | Un saut par SUIVANTE (±1), DEPEND_DE (fermeture complète) et CONFLIT |  |
| 3. Classement | Score = BM25 normalisé + 0,5 × nombre de noms de la question couverts + 0,25 si la proposition est un départ. Égalité : plus petit `prop_id` |  |
| 4. Second tour | Les noms nouveaux des 10 meilleures propositions deviennent des départs | Au plus 5 noms nouveaux ; 2 tours au total |
| 5. Contraintes | MEME confirmé : chercher les deux noms. IGNORER_SOURCE : retirer les propositions de la pièce |  |
| 6. Fermeture et coupe | Ajouter une proposition avec toutes ses dépendances et ses conflits. Si le tout dépasse le budget, ne pas l'ajouter | 150 propositions ; 3 500 jetons (6 000 en A0 et A1) |
| 7. Ordre du contexte | Propositions groupées par pièce, dans l'ordre du document. Pièces classées par leur meilleur score |  |

**Questions de suite.** Si la question n'a aucun nom (« et ensuite, qu'a-t-il fait ? »), la recherche reprend les noms de la question précédente. Les propositions citées au tour précédent entrent toujours dans le contexte, avec la marque `citee_avant`.

**Trace.** Pour chaque proposition rendue : départ par nom, départ par texte, type de saut, numéro de tour. La trace entre dans la table `trace`.

**Mesure.** Rappel des propositions justificatives dans le budget, par type de question et par niveau de dégradation. Aucun embedding dense en v1.

## 8. Entrée du modèle

La fonction `anonymize.encode` transforme un exemple JSON (section 4) en une séquence de jetons et en tables d'indices. C'est la seule entrée du modèle.

### Séquence

```text
[BOS]
[H] message précédent [/H]            au plus 3 messages, du plus ancien au plus récent
[Q] question [/Q]
[REL] ⟨PER_17⟩ ⟨R:INITIALES_DE⟩ ⟨PER_203⟩ … [/REL]      A0 seulement, au plus 200 triplets
[P] ⟨PIECE:PV_AUDITION⟩ ⟨RANG:1⟩ [OCR_BAS]? [CITEE_AVANT]? [CONFLIT]? [DEPEND]?  texte de la proposition  [/P]
…  une ligne [P] … [/P] par proposition, dans l'ordre de la recherche
[SORTIE]
pas de sortie 1, pas de sortie 2, …, FIN
```

La question et l'historique sont avant le contexte : un modèle causal lit ainsi chaque proposition en connaissant la question. Le même ordre sert en B.

### Jetons spéciaux

| Famille | Jetons |
| --- | --- |
| Structure | [BOS] [H] [/H] [Q] [/Q] [REL] [/REL] [P] [/P] [SORTIE] [MASK] [NOUVEAU] |
| Slots, variante B | ⟨PER⟩ ⟨ORG⟩ ⟨LIEU⟩ ⟨REF⟩ ⟨AUTRE⟩ ⟨NUM⟩ ⟨DATE⟩ |
| Slots, variantes A | ⟨PER_0⟩ … ⟨PER_255⟩, et de même pour ORG, LIEU, REF, AUTRE : 1 280 vecteurs. Pour ⟨NUM⟩ et ⟨DATE⟩ : un vecteur de réservoir par valeur distincte, ajouté aux attributs |
| Métadonnées | ⟨PIECE:type⟩ (8 types), ⟨RANG:0⟩ … ⟨RANG:4⟩, [OCR_BAS], [CITEE_AVANT], [CONFLIT], [DEPEND] |
| Relations en jetons, A0 seulement | ⟨R:nom⟩ pour les relations 2 à 14 |
| Lexique de sortie | Section 10. Chaque jeton du lexique a aussi un vecteur d'entrée, pour les pas déjà produits |

**Tokenizer.** En B : BPE par octets, 32 000 jetons, casse gardée, entraîné sur le corpus déjà anonymisé. Il ne voit donc aucun nom détecté. En A : le tokenizer du modèle de base, sans changement. Les jetons nouveaux ont leur propre table de vecteurs, hors du modèle de base ; l'entrée passe par `inputs_embeds`.

### Tables d'indices

T est la longueur de la séquence, P le nombre de propositions, N le nombre de noms distincts, S le nombre de pas de sortie.

| Table | Forme | Contenu |
| --- | --- | --- |
| `input_ids` | T | Jetons |
| `segment` | T | 0 : historique et question ; 1 : contexte ; 2 : sortie |
| `prop_idx` | T | 0, ou le numéro de la proposition (1 à P) |
| `name_idx` | T | 0, ou le numéro local du nom (1 à N) |
| `val_idx` | T | 0, ou le numéro de la valeur (nombres et dates) |
| `num_attr` | T × 4 | Unité, ordre de grandeur, rang, signe ; 0 si absent |
| `NN` | (N+1) × (N+1) | Masque de bits des relations 1 à 14 entre deux noms. La ligne 0 est vide |
| `PP` | (P+1) × (P+1) | Masque de bits des relations 16 à 24 entre deux propositions. La ligne 0 est vide |
| `fin_prop` | P | Position du jeton [/P] de chaque proposition |
| `pos_mention`, `pos_nombre` | M, K | Positions des mentions et des nombres ; pour un nombre, sa proposition |
| `cible`, `masque` | S, S × (L + P + K + M) | Pas de référence, et masque de grammaire de chaque pas |

- La relation 15 (MEME_NOMBRE) se calcule à la volée : `val_idx` égaux et non nuls.
- **Un pas de sortie hérite des indices de sa cible.** Après un pointeur vers la proposition 12, ce pas reçoit `prop_idx = 12`. Après un pointeur vers une mention, il reçoit son `name_idx`. Les biais d'attention relient ainsi le décodeur à ce qu'il a déjà cité, sans aucune étiquette.
- Les positions sont continues de 0 à T − 1, avec RoPE sur tous les jetons. Aucun jeton n'est « sans position ».
- Limites : T ≤ 4 096 en B (8 192 en A) ; P ≤ 150 ; S ≤ 96.

## 9. Modèle

Trois variantes partagent les mêmes têtes de sortie, la même grammaire et le même vérificateur. Elles diffèrent par le tronc et par la façon de donner les relations.

|  | A0 | A1 | B |
| --- | --- | --- | --- |
| Tronc | Modèle pré-entraîné ouvert de 0,4 à 0,6 milliard de paramètres (Qwen ou SmolLM), puis 1,5 milliard ; LoRA de rang 16 sur l'attention et le MLP | Comme A0 | De zéro, tailles ci-dessous |
| Masque | Causal | Causal | Prefix-LM : entrée bidirectionnelle, sortie causale |
| Relations | Jetons dans l'en-tête [REL] | Biais d'attention, à zéro au départ | Biais d'attention |
| Slots de noms | Réservoir de 256 par type | Réservoir de 256 par type | Un vecteur par type |
| Vecteur de proposition | État caché de [/P] | État caché de [/P] | Attention pooling |
| Amnésie des poids | Non | Non | Oui, mesurée par les canaris |
| Équivariance | Apprise | Apprise | Exacte |

**Tailles de B.** Pré-norme RMSNorm, RoPE, SwiGLU, aucune couche de biais, vecteurs d'entrée liés à la tête de langage.

| Taille | Couches | Dimension | Têtes | MLP caché | Paramètres |
| --- | --- | --- | --- | --- | --- |
| B-S | 12 | 768 | 12 | 2 048 | ≈ 110 M |
| B-M | 16 | 1 024 | 16 | 2 736 | ≈ 235 M |

Commencer par B-S. Passer à B-M seulement si B-S passe le seuil de la phase 6.

### Attention relationnelle (A1 et B)

```text
score(i, j) = q_i · k_j / √d_tête  +  Σ_r δ[couche, tête, r] · R_r(i, j)          r = 1 … 24

R_r(i, j) = bit r de NN[name_idx[i], name_idx[j]]        r = 1 … 14
          = (val_idx[i] = val_idx[j] ≠ 0)                r = 15
          = bit r de PP[prop_idx[i], prop_idx[j]]        r = 16 … 24
```

- δ a la forme couches × têtes × 24. Départ à zéro. Aucune décroissance de poids sur δ.
- **Version de référence** (`attention.py`, `dense`). Construire le biais T × T par lecture des tables, l'ajouter aux scores, appliquer le masque. Lente, simple, utilisée dans tous les tests.
- **Version rapide** (`attention.py`, `flex`). Avec FlexAttention : à chaque couche, calculer deux petites tables, `BN` (têtes × (N+1) × (N+1)) et `BP` (têtes × (P+1) × (P+1)), en sommant les δ des bits présents. Le `score_mod` ajoute `BN[b, h, name_idx[q], name_idx[k]] + BP[b, h, prop_idx[q], prop_idx[k]]` et le terme des nombres. Rien de taille T × T n'est gardé en mémoire.
- **Masque prefix-LM** (`mask_mod`). Le jeton q voit le jeton k si `segment[k] < 2`, ou si `segment[q] = 2` et `k ≤ q`. Les jetons d'entrée ne voient donc jamais la sortie : l'entrée est encodée une fois, puis mise en cache.
- **Test obligatoire.** Les deux versions donnent les mêmes sorties à 1e-4 près sur 100 entrées aléatoires. Si FlexAttention pose un problème, garder la version de référence avec T ≤ 2 048 et le noter au journal.
- **En A1.** Envelopper chaque module d'attention du modèle de base pour ajouter le biais de sa couche au masque additif. Le biais est dense : limiter le contexte à 2 500 jetons.

### Vecteurs pointés

- Proposition, en A : `r_p` = état caché de la dernière couche au jeton [/P], puis une couche linéaire et RMSNorm.
- Proposition, en B : `r_p` = Σ α_j h_j sur les jetons de la proposition, avec α = softmax(w · h_j), puis linéaire et RMSNorm.
- Mention et nombre : `h_m`, `h_n` = état caché de la dernière couche à la position du slot.

### Têtes de sortie

```text
z_lex = W_lex h_t                                          L jetons du lexique
s_p   = τ_P · (A_P h_t) · (B_P r_p) / √256 + b_P           une valeur par proposition
s_n   = τ_N · (A_N h_t) · (B_N h_n) / √256 + b_N           une valeur par nombre
s_m   = τ_M · (A_M h_t) · (B_M h_m) / √256 + b_M           une valeur par mention
a_t   = softmax( [z_lex ; s_p ; s_n ; s_m] + masque_t )

sélection :  P(p utile) = sigmoïde(w_s · r_p + b_s)
```

- A et B projettent vers 256 dimensions. τ (départ 1) et b (départ 0) sont des scalaires appris par famille (C12).
- **Pointeur de mention = pointeur de nom (C1).** La probabilité d'un nom est la somme des probabilités de ses mentions autorisées. La perte est −log de cette somme. Au décodage, le code choisit le nom de plus grande somme, puis sa mention la plus probable comme représentante.
- **Tête de langage.** Entraînée au pré-entraînement de B : vocabulaire de 32 000 jetons, plus un pointeur vers les slots antérieurs et le vecteur [NOUVEAU]. Au réglage fin, elle est gardée pour la synthèse raisonnée, sous masque (section 10 bis).

### Entrée du décodeur et décodage

- Après un jeton du lexique : son vecteur d'entrée.
- Après un pointeur : vecteur du genre (proposition, nombre, mention) + `W_in` × vecteur pointé. Le gradient passe. À l'entraînement, le vecteur pointé est celui de la référence.
- Décodage glouton sous masque ; faisceau de 4 en option. Limite de 96 pas : à 90 pas, le masque n'autorise plus que le chemin le plus court vers FIN.
- Abstention : si P(ABSTENTION) au premier pas dépasse un seuil réglé sur la validation, le code choisit ABSTENTION.

## 10. Grammaire, automate et masque

La sortie est une suite de pas. Chaque pas est un jeton du lexique ou un pointeur. Un automate écrit en code donne, à chaque pas, l'ensemble des pas autorisés. Le même automate sert à préparer les données, à décoder et à relire la sortie dans le vérificateur.

### Lexique : 25 jetons

| Famille | Jetons |
| --- | --- |
| Structure | FIN, ABSTENTION |
| Connecteurs | ET, MAIS, DONC, EN_REVANCHE, PAR_AILLEURS |
| Calcul | CALCUL, FIN_CALCUL, +, −, ×, ÷, MIN, MAX |
| Conflit | CONFLIT, FIN_CONFLIT, DECLARATION |
| Identité | SAME, SANS_PREUVE, NOTE_SAME, NOTE_DIFF, ASK_SAME |
| Navigation (réservés, toujours masqués en v1) | OUVRIR, RETOUR |

La synthèse annonçait environ 50 jetons. La liste fermée en compte 25. Un ajout au lexique est une décision de Raphael : chaque jeton est une chose que le modèle peut affirmer sans citation.

### Écriture de chaque segment

```text
CITE(p)                  →  P
CALCUL(expr)             →  CALCUL  (N | op)+  FIN_CALCUL              expression postfixe
CONFLIT(p, p′, …)        →  CONFLIT  P  P+  FIN_CONFLIT
CONFLIT(déclaration, p)  →  CONFLIT  DECLARATION  M  M  P+  FIN_CONFLIT
SAME(a, b, p)            →  SAME  M  M  P
SAME(a, b)               →  SAME  M  M  SANS_PREUVE
NOTE_SAME(a, b)          →  NOTE_SAME  M  M
NOTE_DIFF(a, b)          →  NOTE_DIFF  M  M
ASK_SAME(a, b)           →  ASK_SAME  M  M

Réponse  →  ABSTENTION FIN   |   segment (connecteur segment)* FIN
```

### Règles du masque

| État | Pas autorisés |
| --- | --- |
| Début | ABSTENTION, ou le début de tout segment |
| Après un segment complet | Un connecteur, ou FIN |
| Après un connecteur | Le début de tout segment ; jamais FIN, jamais ABSTENTION |
| CITE | Toute proposition du contexte non encore citée |
| CALCUL, opérande | Un nombre d'une proposition déjà citée |
| CALCUL, opérateur | Seulement si la pile a 2 éléments ou plus et si l'algèbre des unités l'accepte |
| CALCUL, fin | Seulement si la pile a 1 élément et si un opérateur au moins a été appliqué ; 12 pas au plus |
| CONFLIT, premier P | Une proposition qui a une arête CONFLIT dans le contexte |
| CONFLIT, P suivants | Une proposition reliée au premier P par une arête CONFLIT |
| CONFLIT DECLARATION | Deux mentions dont les noms ont une contrainte de l'utilisateur, puis une proposition ou plus |
| SAME, ASK_SAME | Deux mentions de noms différents et de même type, sans contrainte DIFFERENT. Pour SAME, la preuve P contient une mention de l'un des deux noms |
| NOTE_SAME, NOTE_DIFF | Deux mentions du dernier message de l'utilisateur, de noms différents |

- **Aucune impasse.** L'automate n'ouvre un segment que s'il peut le finir : CALCUL demande deux nombres cités d'unités compatibles ; CONFLIT demande une arête ou une contrainte ; SAME demande deux noms du même type.
- **Le masque connaît les vraies valeurs.** Il tourne dans le code, hors du modèle. Il interdit par exemple ÷ quand le diviseur vaut zéro.

### Algèbre des unités

| Opération | Condition | Unité du résultat |
| --- | --- | --- |
| +, −, MIN, MAX | Même unité | Cette unité |
| DATE − DATE |  | Durée en jours |
| DATE + durée, DATE − durée |  | DATE |
| × | Un opérande est un pourcentage ou un rapport sans unité | Unité de l'autre opérande |
| ÷ | Même unité | Rapport sans unité |
| ÷ | Le diviseur est un pourcentage ou un rapport | Unité du dividende |
| Tout autre cas |  | Interdit par le masque |

Un pourcentage vaut sa valeur divisée par 100. Le modèle n'écrit aucune constante et ne compte rien : tous les opérandes sont des nombres cités. Le résultat est calculé en décimal exact par le vérificateur.

### Ordre des suites de référence

Plusieurs suites peuvent dire la même chose. Les données d'entraînement en gardent une seule, toujours construite ainsi :

1. NOTE_SAME et NOTE_DIFF d'abord, si le message de l'utilisateur déclare une identité.
2. Les citations dans l'ordre de la chaîne de raisonnement du jeu de données ; sinon dans l'ordre du contexte.
3. Chaque SAME juste avant la première citation qui en a besoin (règle d'ancrage, section 11).
4. Un bloc CONFLIT à la place d'un CITE quand la proposition a un conflit dans le contexte.
5. CALCUL après ses citations, précédé de DONC.
6. Connecteur ET par défaut. MAIS ou EN_REVANCHE devant un segment opposé ; PAR_AILLEURS devant un segment sans nom commun avec le précédent. Seuls les gabarits du corpus synthétique et l'enseignant produisent ces trois connecteurs.

## 10 bis. Synthèse raisonnée

Après les citations, le modèle écrit une synthèse de 1 à 8 phrases. Les mots sont libres ; les noms, nombres et dates sont des pointeurs vers les sources déclarées de la phrase. Le masque applique cette règle pendant le décodage : c'est une garantie par construction, pas un contrôle après coup.

### Grammaire

```text
Réponse  := Segment (Connecteur Segment)* [ Synthèse ] FIN   |   ABSTENTION FIN
Synthèse := SYNTHESE  PhraseS+  FIN_SYNTHESE                    8 phrases au plus
PhraseS  := SOURCES  P{1,4}  DEBUT  Élément+  FIN_PHRASE         40 mots au plus
Élément  := mot  |  M  |  N  |  CALCUL (N | op)+ FIN_CALCUL
```

Le lexique d'actions passe de 25 à 30 jetons : SYNTHESE, FIN_SYNTHESE, SOURCES, DEBUT, FIN_PHRASE. Le mode citation ne change pas.

### Règles du masque

| Pas | Autorisé |
| --- | --- |
| SOURCES P | Propositions déjà citées dans cette réponse, distinctes, de 1 à 4. Les dépendances DEPEND_DE d'une source comptent comme sources |
| mot | Jetons qui forment un mot de la liste V (ci-dessous). Contrainte mot par mot avec un arbre de préfixes sur le vocabulaire BPE |
| M | Une mention d'un nom présent dans les sources de la phrase. Même pointeur de nom qu'en section 9 : somme des mentions du même nom |
| N | Un nombre ou une date des sources de la phrase |
| CALCUL | Opérandes pris dans les sources de la phrase ; mêmes règles d'unités qu'en section 10 |
| Négation (ne, n', pas, aucun, aucune, jamais, non, ni, nullement, sans) | Seulement si une source de la phrase contient une marque de négation |
| Majuscule | Seulement pour le premier mot après DEBUT |
| FIN_PHRASE | Seulement si la phrase contient au moins un pointeur M ou N |

**Liste V.** Mots du corpus de pré-entraînement déjà anonymisé, vus au moins 50 fois hors des slots, en minuscules. Le code retire ensuite : tout mot qui contient un chiffre ; les nombres en lettres (zéro à milliard, ordinaux, demi, double, moitié, triple, dizaine, centaine) ; les mois et les jours ; les sigles ; les mots de la liste des prénoms et des noms de famille courants. Taille attendue : 30 000 à 50 000 mots. V est un fichier versionné ; une modification de V est une décision de Raphael.

**Numéros.** Pour l'affichage interne et les exemples, les noms sont numérotés par type (⟨personne2⟩, ⟨société1⟩, ⟨montant1⟩), avec la table de la conversation. En variante A, le modèle lit ces numéros ; ils sont tirés au hasard à chaque exemple. En variante B, il ne les lit pas : il pointe vers des mentions, et l'identité passe par les relations.

### Modèle

- Les mots de la synthèse viennent de la tête de langage, sous masque. En B, la tête du pré-entraînement est gardée. En A, c'est la tête de Qwen ou de SmolLM.
- La softmax unique devient [lexique d'actions ; mots autorisés ; pointeurs], avec une température et un biais par famille.
- Un pas « mot » n'hérite d'aucun indice. Un pointeur M ou N hérite des indices de sa cible, comme en section 8.

### Rendu

Le code remplace chaque pointeur par la chaîne de la mention, et chaque N par la valeur écrite dans sa source. Style distinct, étiquette « synthèse du modèle ». Après chaque phrase : un lien ※ par source, avec pièce et page. Un clic affiche la phrase source et ses dépendances.

### Données

| Source | Construction de la cible | Volume visé |
| --- | --- | --- |
| Corpus synthétique | Le générateur écrit la synthèse depuis le graphe de faits, avec au moins 5 formulations par type de relation ; sources et pointeurs connus | 2 à 3 phrases par question |
| Textes publics (Légifrance, Judilibre, HotpotQA) | Le modèle enseignant écrit 1 à 3 phrases avec les numéros de leurs sources. Le code détecte les noms, nombres et dates, les relie par chaîne exacte à une mention des sources déclarées, et les remplace par des pointeurs. Il rejette la phrase si un élément ne se relie pas, si un mot sort de V, ou si une négation n'a pas de source négative | 30 000 phrases |

Perte : la même entropie croisée que pour les actions, sur tous les pas de la synthèse, avec le masque. Les exemples sans synthèse restent dans le mélange (30 %), pour les questions simples.

### Évaluation

- **T11 (CI).** 100 000 décodages aléatoires en mode synthèse : aucun chiffre, aucun mot hors de V, et chaque nom, nombre et date affiché appartient aux sources de sa phrase.
- **Exactitude des relations.** Sur le corpus synthétique de test, un juge classe chaque phrase : exacte, personnes inversées, verbe faux, conclusion non soutenue. Le juge est un LLM utilisé seulement pour l'évaluation, jamais dans le produit, calibré sur 200 phrases annotées à la main. Mesures publiées : taux de phrases exactes et taux d'inversion.
- **Comparaison.** Même mesure pour le RAG classique, plus son taux de noms, nombres et dates inventés.
- **Utilité.** Test utilisateur : citations seules contre citations et synthèse, sur le même dossier.

### Ordre

La synthèse s'entraîne en phase 4 bis, après le seuil de A0 en mode citation, puis en phase 6 pour B. Seuil de départ en phase 4 bis : 85 % de phrases exactes et moins de 3 % d'inversions sur le niveau 0.

**Limite.** Le masque ferme les faits, pas les relations. Les mots libres peuvent aussi porter un savoir général du monde, jamais un savoir sur une personne : la sonde d'amnésie mesure aussi la synthèse.

## 11. Vérificateur et rendu

Le vérificateur est du code pur. Il reçoit la suite de pas du modèle et rend le texte affiché. Toutes les garanties « quels que soient les poids » sont ici et dans le masque.

1. **Relecture.** Repasser la suite dans l'automate. Une suite refusée ne peut pas arriver sous masque ; si elle arrive, afficher une erreur et l'écrire dans la trace.
2. **Dépendances.** Pour chaque proposition citée, ajouter toute la fermeture DEPEND_DE, affichée avant la citation, dans le style « contexte ».
3. **Calculs.** Contrôler que chaque opérande vient d'une proposition citée. Calculer en décimal exact. Afficher la formule entière.
4. **Conflits.** Pour chaque proposition citée, lire ses arêtes CONFLIT dans toute la base, pas seulement dans le contexte. Si un autre côté n'est pas affiché, ajouter le bloc CONFLIT. Les sources ignorées par l'utilisateur restent exclues.
5. **Ancrage** (ci-dessous).
6. **Passages non cités.** Ajouter le bloc « Autres passages pertinents » : propositions de probabilité de sélection ≥ seuil, non citées, 10 au plus, avec leurs dépendances. Le seuil est réglé sur la validation pour un rappel de 0,95.
7. **Rendu.** Lire chaque texte original dans le stock par `prop_id`. Afficher la pièce et la page. Sous le seuil de confiance OCR : « à vérifier sur la page X ».
8. **Contraintes.** Après NOTE_SAME ou NOTE_DIFF : enregistrer la contrainte, puis refaire une fois la recherche et la réponse.
9. **Trace.** Écrire la ligne de la table `trace`.

### Règle d'ancrage (remplace la « règle d'identité »)

Le code ne sait pas qui est qui. Il sait seulement si deux chaînes sont égales. La règle utilise cela, et rien d'autre.

- **Liens sûrs.** Deux éléments (la question, ou une proposition citée) sont liés s'ils contiennent le même nom (même norme), ou deux noms d'une contrainte MEME de l'utilisateur, ou deux noms d'un SAME écrit par le modèle dans cette réponse.
- **Ancrée.** Une proposition citée est ancrée si une chaîne de liens sûrs la relie à la question.
- **Non ancrée, avec un nom ressemblant.** Si elle contient un nom relié par une relation 2 à 11 à un nom d'un élément ancré, le vérificateur ajoute : « Lien non confirmé : « Y » (cette citation) et « X ». Ressemblance : [relation]. » La proposition compte ensuite comme ancrée pour la suite du parcours.
- **Non ancrée, sans aucun nom.** Aucune note : c'est une règle ou un énoncé général.
- **Non ancrée, avec d'autres noms.** Le vérificateur ajoute : « Cette citation ne nomme aucune personne ni entité de la question. »
- La règle ne s'applique pas si la question et l'historique n'ont aucun nom.

La garantie devient : toute citation reliée à la question autrement que par un nom identique porte une marque visible. C'est vrai quels que soient les poids.

### Gabarits d'affichage

Les gabarits sont des chaînes fixes dans `verify/render.py`. Les noms entre guillemets viennent des mentions du contexte ou de la question.

| Pas | Texte affiché |
| --- | --- |
| ET, MAIS, EN_REVANCHE, PAR_AILLEURS | « et », « mais », « en revanche », « par ailleurs » |
| DONC | « donc », avec l'étiquette « inférence du modèle » |
| ABSTENTION | « Les passages trouvés ne répondent pas à cette question. » Le bloc des passages non cités suit, s'il n'est pas vide |
| SAME avec preuve | « Hypothèse : « A » et « B » sont la même personne. Source : « … » (pièce, page). » |
| SAME sans preuve | « Hypothèse fondée sur la seule ressemblance des noms : « A » et « B ». » |
| NOTE_SAME, NOTE_DIFF | « Noté : « A » et « B » sont la même personne (votre déclaration). » ; de même pour « des personnes différentes » |
| ASK_SAME | « « A » et « B » sont-ils la même personne ? » |
| CALCUL | « Calcul : 1 200 € + 300 € = 1 500 € », chaque opérande relié à sa citation |
| CONFLIT | « Conflit entre sources. » puis chaque source avec son extrait ; puis « Rang : … » si les deux rangs sont connus et différents |
| CONFLIT DECLARATION | « Vous avez dit que « A » et « B » sont la même personne. » puis les citations |

Pour un type autre que PER, « la même personne » devient « la même organisation », « le même lieu » ou « la même chose ».

**Test de propriété.** Pour toute suite tirée au hasard sous masque, chaque caractère affiché vient de l'un de ces quatre ensembles : texte original d'une proposition du contexte ou de ses dépendances et conflits, gabarit fixe, nom d'une mention du contexte ou de la question, résultat d'un calcul sur des nombres cités.

## 12. Données d'entraînement

Il y a trois jeux de données : le corpus synthétique (phase 1), les données de réglage fin (phase 4) et le corpus de pré-entraînement (phase 5). Tous passent par l'anonymiseur de la section 6 : les erreurs de détection sont ainsi les mêmes qu'à l'inférence.

### Corpus synthétique (phase 1)

| Élément | Valeur de départ |
| --- | --- |
| Monde d'un dossier | 6 à 20 personnes avec un rôle ; 2 à 5 sociétés ; 3 à 8 lieux ; 15 à 40 événements datés (audition, vol, virement, appel, rencontre, signature, contrôle, interpellation, constatation), chacun avec participants, date, heure, lieu, montants |
| Formes d'un nom | Nom complet ; « NOM Prénom » ; initiales ; nom seul ; titre et nom ; surnom introduit par « dit » |
| Cas durs | 30 % des dossiers avec alias ; 20 % avec deux personnes de même nom de famille ; 5 % avec deux personnes de même nom complet |
| Versions contradictoires | 30 % des dossiers : un événement a deux versions (heure, montant ou personne), dites par deux témoins |
| Pièces | 8 à 25 par dossier. Phase 1 : gabarits, au moins 5 formulations par type de fait et par type de pièce. Phase 7 : rédaction par un LLM, puis contrôle |
| Contrôle | Chaque nom, nombre et date d'une phrase appartient aux faits déclarés de la phrase. Sinon la pièce est rejetée |
| Noms | Prénoms et noms inventés ou courants ; exclure tout nom complet présent dans la liste des personnes de Wikidata |
| Séparation entraînement et test | Par dossier. Gabarits, réservoirs de noms et graines différents pour le test |

| Type de question | Part | Cible |
| --- | --- | --- |
| Fait simple | 20 % | Un CITE |
| Plusieurs étapes | 25 % | 2 à 4 CITE en chaîne |
| Identité | 15 % | SAME avec preuve, ou sans preuve, puis CITE |
| Fait absent | 10 % | ABSTENTION |
| Conflit | 10 % | Bloc CONFLIT |
| Calcul | 10 % | CITE puis CALCUL : somme, écart, durée entre deux dates, minimum, maximum |
| Dialogue | 10 % | Question de suite avec pronom ; correction juste ou fausse de l'utilisateur (NOTE_SAME, NOTE_DIFF, CONFLIT DECLARATION) ; ASK_SAME quand deux personnes sont possibles sans preuve |

Environ 40 questions par dossier, soit 80 000 exemples d'entraînement pour 2 000 dossiers.

### Données de réglage fin (phase 4)

| Source | Langue | Conversion | Apprend | Poids |
| --- | --- | --- | --- | --- |
| Corpus synthétique | fr | Vérité terrain directe | Toutes les actions | 40 % |
| HotpotQA, réglage « distracteurs » | en | Une phrase = une proposition ; phrase justificative = CITE ; la réponse courte est ignorée | Chaînes de citations | 20 % |
| FQuAD, PIAF | fr | La phrase qui contient l'extrait = CITE ; ajouter 3 paragraphes du même article comme distracteurs | Citation en français | 15 % |
| Légifrance, Judilibre | fr | Questions d'un modèle enseignant (ci-dessous) | Texte juridique | 15 % |
| FinQA | en | Programme de référence → CALCUL postfixe ; garder seulement les programmes sans constante, avec +, −, ×, ÷ | Calcul sur nombres cités | 5 % |
| SQuAD 2.0, questions sans réponse | en | ABSTENTION | Abstention sur texte réel | 5 % |
| TAB | en | Aucune : évaluation seulement | Rappel de la détection | 0 % |

**Modèle enseignant.** Il reçoit des propositions numérotées d'un texte public. Il rend un JSON : question, numéros des propositions justificatives, connecteurs. Le code garde l'exemple si les numéros existent, s'il y a 4 justificatives au plus, et si un second passage confirme deux choses : la question a une réponse avec les justificatives seules, et n'en a pas sans elles. Cible : 20 000 exemples. L'enseignant voit seulement des textes publics.

**Licences.** L'agent lit la licence de chaque jeu avant de l'utiliser et l'écrit dans `DATA_LICENSES.md`. Une licence non commerciale (à vérifier pour FQuAD) est acceptable pour la recherche ; l'agent la signale.

### Exemples négatifs et difficiles

- **Contexte réel.** Le contexte de chaque exemple vient de la vraie recherche de la section 7. Dans 80 % des exemples, le code ajoute les justificatives manquantes. Dans les 20 % restants, si une justificative manque, la cible devient ABSTENTION.
- **Abstention.** 10 à 15 % des exemples : le code retire les justificatives et leurs doublons.
- **Conflit injecté.** Le code copie une justificative dans une nouvelle pièce d'un autre rang et change une valeur. La cible devient un bloc CONFLIT.
- **Contrefactuel.** 5 % des exemples : le code change une valeur ou inverse une règle dans la justificative. La cible reste la citation de cette proposition. Une proposition de forme « habituelle » est ajoutée dans une pièce sans rapport.
- **Tirage des indices.** Les indices de noms et de valeurs sont tirés de nouveau à chaque époque.

### Corpus de pré-entraînement (phase 5)

- **Taille.** 2,5 milliards de jetons : c'est le plus petit budget de KLLM, et l'effet d'amnésie y est déjà mesuré dès 135 M de paramètres.
- **Sources, 70 % français.** Wikipédia, Légifrance (LEGI, JORF), décisions de justice en données ouvertes, textes de l'Union européenne, livres du domaine public.
- **Sources, 30 % anglais.** Wikipédia, textes de l'Union européenne, arrêts de la CEDH, livres du domaine public.
- **Chaîne.** Nettoyer ; couper en fenêtres de 2 048 jetons ; détecter et propager les noms ; remplacer noms et nombres ; calculer les relations ; écrire en Parquet. Dans la moitié des documents, chaque phrase est entourée de [P] … [/P], avec les relations 16 à 18 et 23.
- **Coût de la détection.** C'est l'étape la plus chère. Mesurer d'abord le débit de chaque détecteur sur 10 millions de jetons. Si GLiNER demande plus de 3 jours de GPU pour tout le corpus, l'appliquer à 10 % du corpus, mesurer ce que les autres détecteurs ratent, et écrire la décision au journal.
- **Canaris.** Voir section 14.

## 13. Entraînement

Il y a trois entraînements : le réglage fin de A0 puis A1 (phase 4), le pré-entraînement de B (phase 5), le réglage fin de B (phase 6). La perte de réglage fin est la même pour les trois variantes.

### Perte de réglage fin

```text
L = L_actions + 0,5 · L_sélection

L_actions   = moyenne sur les pas de sortie de  −log a_t[pas de référence]
              (softmax unique sous le masque de l'automate ; pour un pas de mention :
               −log de la somme des probabilités des mentions du nom de référence)
L_sélection = entropie croisée binaire sur les propositions ; positives = justificatives ;
              poids des positives = nombre de négatives / nombre de positives, borné à 10
```

Le masque de chaque pas est calculé par l'automate dans le chargeur de données. Un test contrôle que chaque pas de référence est autorisé par son masque.

### Réglages par phase

|  | Phase 4 : A0 et A1 | Phase 5 : pré-entraînement B-S | Phase 6 : réglage fin de B |
| --- | --- | --- | --- |
| Poids entraînés | LoRA (rang 16, alpha 32, abandon 0,05) ; en entier : vecteurs des jetons nouveaux, têtes, `W_in`, δ en A1 | Tous | Tous ; tête de langage gardée pour la synthèse |
| Optimiseur | AdamW, bêtas 0,9 et 0,999 | AdamW, bêtas 0,9 et 0,95 | AdamW, bêtas 0,9 et 0,999 |
| Pas d'apprentissage | 2e-4 pour LoRA ; 1e-3 pour les modules nouveaux | Pic à 6e-4, cosinus jusqu'à 6e-5 | 1e-4 pour le tronc ; 5e-4 pour les têtes |
| Échauffement | 500 pas | 2 000 pas | 500 pas |
| Décroissance de poids | 0,01 | 0,1 ; aucune sur δ, les normes et les vecteurs d'entrée | 0,05 ; aucune sur δ |
| Lot | 16 contextes (avec accumulation) | 64 séquences de 2 048 jetons | 32 contextes |
| Durée | 3 époques | 2 passages sur le corpus, masques tirés de nouveau | 5 époques |
| Abandon | 0,05 (LoRA) | 0 | 0,1 |
| Autres | bf16, norme du gradient bornée à 1,0 | bf16, `torch.compile`, norme bornée à 1,0 | bf16, norme bornée à 1,0 |

**A1** part du point de contrôle A0 : retirer l'en-tête [REL] des entrées, ajouter δ à zéro, entraîner 2 époques.

### Objectif de pré-entraînement de B (C6, C13)

Chaque séquence est tirée dans l'un des deux modes, à parts égales.

- **Mode causal.** Toute la séquence est en segment 2. Le modèle prédit chaque jeton suivant.
- **Mode préfixe.** Le code coupe la fenêtre à une fin de phrase, entre 25 % et 75 % de sa longueur. Le préfixe est en segment 1 (bidirectionnel) ; la suite est en segment 2 (causale). Le modèle prédit chaque jeton de la suite. Dans le préfixe, 15 % des jetons sont remplacés par [MASK] et prédits.

| Jeton à prédire | Ce que le modèle prédit |
| --- | --- |
| Mot ordinaire | Le mot, parmi les 32 000 jetons |
| Slot de nom | Son type (c'est un jeton du vocabulaire), puis un pointeur : vers une autre mention du même nom, ou vers [NOUVEAU] s'il n'y en a pas. Mode causal : mentions antérieures. Mode préfixe : toutes les mentions non masquées |
| Nombre ou date | Son type, son unité, son ordre de grandeur, puis un pointeur vers une valeur égale ou vers [NOUVEAU] |

```text
L_pré = L_mots + 1,0 · L_pointeur + 0,5 · L_attributs
```

Un slot remplacé par [MASK] a `name_idx`, `val_idx` et `num_attr` à zéro en entrée. Sinon la relation MEME_CHAINE donne la réponse.

### Ordre de lancement et coût

1. **Essai à blanc.** Avant chaque entraînement : 200 pas sur 1 000 exemples. La perte baisse ; un point de contrôle se recharge ; le test T1 passe.
2. **Mesure du débit.** 20 minutes à pleine taille. L'agent calcule la durée totale et l'écrit au journal avant de lancer.
3. **Lancement.** Point de contrôle tous les 2 000 pas ; garder les 3 derniers et le meilleur ; reprise après arrêt.

Ordres de grandeur, à remplacer par les mesures : A0 demande 1 à 3 jours sur un GPU de 24 à 48 Go. Le pré-entraînement de B-S demande 1 à 2 jours sur un GPU de 80 Go, sans compter la détection des noms. Le réglage fin de B demande moins d'un jour. Si une durée mesurée dépasse 5 jours, l'agent réduit le nombre d'exemples par époque et le note.

**Dossier de chaque entraînement.** `runs/<date>-<nom>/` contient la copie figée de la configuration, le numéro du commit, la liste des paquets, `metrics.jsonl` et les points de contrôle. Les résultats finaux utilisent 3 graines ; le rapport donne la moyenne et l'écart.

## 14. Évaluation

Il y a deux familles de contrôles : 10 tests en CI, qui doivent passer à chaque commit, et des mesures, qui donnent les nombres de l'article. Les seuils de passage sont dans la section 2.

### Tests en CI

| Test | Ce qu'il contrôle | Résultat attendu |
| --- | --- | --- |
| T1 : permutation | Permuter les indices de noms et de valeurs (lignes et colonnes de `NN`, `name_idx`, `val_idx`) et l'ordre des listes de mentions | En B : mêmes logits à 1e-5 près en float32. En A : l'écart est une mesure, pas un test |
| T2 : anonymiseur | Sur un dossier synthétique, avec les mentions de référence à la place des détecteurs : renommer par une bijection qui garde les relations, puis encoder | Tables égales après mise en ordre des indices par première apparition |
| T3 : bout en bout | Avec les vrais détecteurs et la vraie recherche : renommer tout un dossier | Mesure : part des questions dont l'ensemble des propositions citées change. Aucun seuil |
| T4 : automate | Suites de référence ; décodages aléatoires sous masque | Toutes acceptées ; aucune impasse ; fin en 96 pas au plus |
| T5 : rendu fermé | Test de propriété de la section 11 | Aucun caractère hors des quatre ensembles |
| T6 : attention | Version rapide contre version de référence | Écart ≤ 1e-4 |
| T7 : hors ligne | Toute ouverture de connexion dans les modules d'inférence | Échec du test si une connexion s'ouvre |
| T8 : oubli | Après `ccm forget` | Chaîne absente de l'index, de la base et du fichier brut |
| T9 : déterminisme | Même graine, même entrée | Mêmes fichiers ; même réponse en décodage glouton |
| T10 : masque de référence | Chaque pas de chaque suite de référence | Autorisé par son masque |

T1 trouve une fuite d'étiquette dans le modèle, par exemple un vecteur indexé par le numéro du nom. T2 trouve une fuite dans le code d'encodage. T3 mesure ce que la garantie ne couvre pas : la détection et la recherche.

### Mesures

| Mesure | Définition |
| --- | --- |
| Citation | Précision, rappel et F1 de l'ensemble des propositions citées contre les justificatives ; part des réponses exactes |
| Abstention | Exactitude sur les faits absents ; taux d'abstention à tort sur les questions qui ont une réponse |
| Identité | Précision et rappel des SAME contre les alias de référence ; **taux de fusion à tort** sur les dossiers avec homonymes ; taux de ASK_SAME |
| Conflit | Précision et rappel de la détection à l'ingestion ; taux d'affichage des conflits détectés (100 % par construction) |
| Calcul | Part des résultats exacts |
| Omission | 1 − rappel de (citées + « autres passages ») contre les justificatives ; rappel de la recherche dans le budget |
| Détection | Rappel par type de nom |
| Invention | Noms, nombres et dates de la réponse absents du contexte. Zéro par construction pour le CCM ; mesuré pour le RAG classique |
| Renommage | Résultat de T3 |
| Amnésie | Canaris et sonde en livre fermé (ci-dessous) |
| Coût | Temps par réponse, jetons lus |

Chaque mesure est donnée par type de question et par niveau de dégradation. `eval/report.py` écrit un tableau Markdown par entraînement.

### Amnésie

- **Canaris naturels.** 300 faux faits sur des noms inventés, insérés dans le corpus brut avant l'anonymisation, répétés 1, 10 ou 100 fois (100 canaris par fréquence). Ils mesurent la chaîne telle qu'elle est.
- **Canaris forcés.** 300 autres faux faits, insérés après l'anonymisation, noms en clair. Ils mesurent ce que coûte un nom non détecté, selon sa fréquence.
- **Mesure des canaris.** Sur le point de contrôle pré-entraîné, avec la tête de langage : rang de la vraie fin de phrase parmi 1 000 fins possibles. Taux d'extraction = part des canaris au rang 1.
- **Sonde en livre fermé.** 500 personnes connues, décrites sans leur nom. Mesurer si la tête de langage préfère le vrai attribut. Comparer avec un modèle témoin de même taille, entraîné sur le même texte non anonymisé, 500 millions de jetons chacun.

### Comparaisons de la phase 6

1. RAG classique : le modèle de base de A, réglé pour répondre en texte libre avec des numéros de sources, même recherche.
2. A0, A1, B-S.
3. Ablations sur B-S : sans biais de relations ; avec pivots de noms ; avec biais dépendant de la requête ; avec la clause comme unité de citation.

## 15. Règles pour l'agent

L'agent travaille seul à l'intérieur d'une phase, et s'arrête aux quatre cas listés ci-dessous. Cet onglet fait foi. Si l'onglet ne dit rien, l'agent prend l'option la plus simple et l'écrit au journal.

**L'agent décide seul.**

- Toute valeur marquée « valeur de départ » ou « réglage », si une mesure justifie le changement.
- Les versions des bibliothèques, la structure interne des modules, les tests ajoutés.
- L'ordre du travail à l'intérieur d'une phase.

**L'agent ne change pas sans accord de Raphael.**

- Le lexique, la grammaire, la liste des 24 relations, les règles du vérificateur.
- Le texte d'une garantie, ou le résultat attendu d'un test T1 à T10.
- L'usage de toute donnée personnelle réelle, et l'envoi de toute donnée non publique à un service externe.
- L'ordre des phases et leurs seuils.

**L'agent s'arrête et rapporte.**

1. Un seuil de phase n'est pas atteint après trois essais documentés.
2. Un test de garantie (T1, T2, T4, T5, T8) échoue, et la correction demande de changer une règle.
3. Une licence de données n'est pas claire, ou interdit l'usage prévu.
4. Une durée mesurée dépasse 5 jours, ou le budget de calcul fixé.

**L'agent ne fait jamais ceci.**

- Affaiblir un test, ou changer une donnée de référence, pour passer un seuil.
- Entraîner sur un dossier de test, ou régler un gabarit en regardant les résultats de test.
- Écrire une chaîne de nom dans un fichier d'entraînement.
- Mettre un modèle génératif dans `ingest`, `search`, `anonymize` ou `verify`.

**Ce que l'agent écrit.**

- `JOURNAL.md` : une entrée par séance. Date, phase, travail fait, mesures, décisions, écarts avec cet onglet, suite prévue.
- `reports/phase-N.md` à la fin de chaque phase : tableau seuil contre mesure, écarts, risques ouverts, questions pour Raphael.
- Git : une branche par phase, de petits commits, une étiquette `phase-N-ok` quand le seuil passe.

## 16. Décisions qui restent à Raphael

Ces 9 points ne bloquent pas les phases 0 à 3. Les trois premiers bloquent la phase 4.

- [ ] **Budget de calcul.** Quel GPU, combien d'heures, quelle dépense maximale.
- [ ] **Modèle de base de A.** Qwen ou SmolLM. KLLM utilise les architectures SmolLM et LLaMA : SmolLM rend la comparaison plus directe.
- [ ] **Modèle enseignant.** Quel LLM pour les questions sur Légifrance (phase 4) et pour la rédaction des pièces (phase 7) ; local ou par API.
- [ ] **Homonymes exacts.** En v1, deux personnes qui portent exactement la même chaîne (un père et un fils, par exemple) sont un seul nom. Option : limiter un nom à sa pièce et laisser le modèle relier les pièces par SAME. C'est plus sûr en pénal, mais chaque réponse affiche plus d'hypothèses.
- [ ] **Conflits reformulés.** Les garder hors de la v1, ajouter un encodeur de phrases non génératif à l'ingestion, ou donner au modèle une action « conflit supposé ».
- [ ] **Langues.** Pré-entraînement bilingue 70/30, ou français seul avec HotpotQA traduit.
- [ ] **Licences.** Accepter des jeux à licence non commerciale pour la recherche.
- [ ] **Types de pièces.** Faire valider la table des types et des motifs d'en-tête par un praticien.
- [ ] **Publication.** Licence du code et des poids, puisque le plan est de publier un modèle ouvert.
