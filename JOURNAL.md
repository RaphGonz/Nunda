# Journal du projet CCM

Une entrée par séance, la plus récente en bas. Modèle :

```
## AAAA-MM-JJ — Phase N — <titre court>
- **Travail fait :**
- **Mesures :**
- **Décisions :**
- **Écarts avec SPEC.md :**
- **Suite prévue :**
```

Un arrêt (SPEC.md §15) s'écrit dans une entrée avec une ligne **ARRÊT :** qui donne le cas (1 à 4) et le problème.

---

## 2026-10-13 — Phase 0 — Mise en place du dépôt
- **Travail fait :** dépôt git créé (GitHub privé `Nunda`), `CLAUDE.md`, `JOURNAL.md`, `.gitignore`. Aucun code.
- **Mesures :** aucune.
- **Décisions :** le dépôt est à la racine de `Nunda/` ; le paquet Python sera `ccm/` (SPEC.md §3).
- **Écarts avec SPEC.md :** aucun. `make` installé via winget (`ezwinports.make`, GNU Make 4.4.1) ; `make test` attend le `Makefile` de la phase 0.
- **Suite prévue :** phase 0 (SPEC.md §2, §3, §4) : `pyproject.toml` avec `uv`, `Makefile` (`make test` = `ruff` + `pytest`), squelette des modules, `ccm/schema.py`, CI verte.

## 2026-10-13 — Phase 0 — Squelette du dépôt, outillage, CI
- **Travail fait :** `pyproject.toml` + `uv.lock` (Python 3.11 figé par `.python-version`), `Makefile` (`setup`, `lint`, `test` = ruff check + ruff format --check + pytest), squelette des paquets de SPEC.md §3 (`ccm/ingest`, `ner`, `graph`, `search`, `anonymize`, `grammar`, `model`, `verify`, `data/worldgen`, `train`, `eval`), `tests/unit|property|golden`, 8 configs YAML lues par `ccm/config.py` (pydantic, clé inconnue refusée), CLI typer vide (`ccm --help`), CI GitHub Actions (Ubuntu + Windows, `make setup` puis `make test`). Ajout de `PLAN.md`, `README.md`, `DATA_LICENSES.md` (vide). `SPEC.md` déjà présent.
- **Mesures :** `make test` local : ruff OK, 12 tests passés. CI GitHub verte (Ubuntu et Windows).
- **Décisions :**
  - SPEC.md §16, prises par Raphael : **budget de calcul : GPU RTX 3090** (heures et dépense maximale pas encore fixées) ; **modèle de base de A : SmolLM** ; **modèle enseignant : LLM local de 7B** (phase 4 Légifrance et phase 7 rédaction des pièces ; modèle exact à choisir, licence à vérifier dans `DATA_LICENSES.md`).
  - Le dossier `ccm/` racine de SPEC.md §3 est la racine du dépôt `Nunda/` (décision de la séance précédente).
  - Dépendances de la séance seulement : pydantic, pyyaml, typer ; dev : ruff, pytest, hypothesis. PyTorch et les autres arrivent avec la phase qui les utilise.
  - Configs : champs `version` et `description` seulement ; chaque phase ajoute ses champs. `model_a0/a1/b_s/b_m` partagent la classe `ModelConfig` pour l'instant.
  - Sous-paquets créés avec `__init__.py` seul ; les modules (`extract`, `bm25`…) s'écrivent avec leur phase.
  - CI Windows : `make` installé par `choco install make`.
- **Écarts avec SPEC.md :** aucun. `schema.py` pas encore écrit (pas dans la tâche du soir).
- **Suite prévue :** `ccm/schema.py` (SPEC.md §4), puis `reports/phase-0.md`.

## 2026-10-13 — Phase 0 — Schémas de données, fin de phase
- **Travail fait :** `ccm/schema.py` (SPEC.md §4) : énumérations, 24 relations et leurs identifiants, lexique de 25 jetons, DDL du stock SQLite et `ouvrir_stock`, modèles pydantic de l'exemple JSON avec contrôles. Exemple de §4 figé dans `tests/golden/exemple_spec.json`. Rapport `reports/phase-0.md`.
- **Mesures :** clone neuf : `make setup && make test` OK ; 26 tests passés ; CI verte Ubuntu et Windows (`63b310d`). Seuil de phase 0 atteint.
- **Décisions :** lexique et relations dans `schema.py` (contrat de `cible`), importés plus tard par `grammar/`. Sens d'une relation orientée = ordre du triplet. Texte de test hypothesis sans substituts Unicode isolés (texte invalide, non sérialisable).
- **Écarts avec SPEC.md :** champs optionnels `signe` et `precision` ajoutés à `MarqueNombre` (exigés par §6, absents de l'exemple §4). Indices de `relations_props` non contrôlés (l'exemple §4 cite une proposition 1 absente). Questions dans `reports/phase-0.md`.
- **Suite prévue :** relecture des écarts de `reports/phase-0.md` avec Raphael (schema, fin de phase faits sans son accord explicite : « bah vas y » mal compris), puis phase 1 (SPEC.md §12, corpus synthétique) : générateur de monde, gabarits, contrôle des faits, graine fixe.

## 2026-10-14 — Phase 0 — Test final : exemple JSON, stock, T7
- **Travail fait :** `tests/unit/test_t7_hors_ligne.py` (T7, SPEC.md §14 et §3) : garde qui refuse `connect`, `connect_ex`, `create_connection`, `getaddrinfo` ; sous ce garde, import neuf de tous les modules de `ingest`, `search`, `anonymize`, `model`, `verify`, chargement de l'exemple JSON de §4, création du stock SQLite. Contrôle statique : aucun import de `socket`, `ssl`, `urllib`, `http`, `requests`, `httpx`, `aiohttp`, `ftplib`, `smtplib` dans ces paquets. Un test vérifie que le garde bloque bien.
- **Mesures :** `make test` : ruff OK, 29 tests passés. Sonde : un module `ccm/verify/_sonde.py` qui ouvre une connexion fait échouer les deux tests T7 (sonde retirée).
- **Décisions :** T7 couvre aujourd'hui l'import des modules (ils sont vides) ; chaque phase ajoutera ses appels d'inférence sous le garde `sans_reseau`. Liste des imports interdits limitée aux bibliothèques réseau ; `transformers` (phase 4) sera contrôlé par le garde dynamique.
- **Écarts avec SPEC.md :** aucun.
- **Suite prévue :** relecture des écarts de `reports/phase-0.md` avec Raphael, puis phase 1 (SPEC.md §12).

## 2026-10-14 — Phase 0 — Écarts tranchés, fin de phase
- **Travail fait :** relecture des écarts de `reports/phase-0.md` avec Raphael. `MarqueNombre` : `signe` obligatoire pour NUM, `precision` pour DATE (chacun interdit pour l'autre genre). `Exemple` : indices de `relations_props` contrôlés. Exemple de SPEC.md §4 et `tests/golden/exemple_spec.json` modifiés avec l'accord de Raphael (`"precision": "JOUR"`, `"relations_props": []`). 6 cas de test ajoutés. Rapport mis à jour ; fusion dans `main` (`231b625`). L'étiquette `phase-0-ok`, posée le 2026-10-13 sur `adda139` sans accord explicite, est déplacée sur `231b625` avec l'accord de Raphael.
- **Mesures :** `make test` : 35 tests passés ; clone neuf `make setup && make test` OK ; CI verte Ubuntu et Windows (`7f04c66`).
- **Décisions (Raphael) :** écart 1 → champs obligatoires par genre ; écart 2 → contrôle des indices, relation retirée de l'exemple ; écart 3 → sens par l'ordre du triplet, validé. Décision de l'agent : le champ de l'autre genre est interdit (un signe de date n'a pas de sens).
- **Écarts avec SPEC.md :** aucun ouvert. §16 : heures et dépense maximale RTX 3090, modèle enseignant 7B exact, toujours à fixer.
- **Suite prévue :** phase 1 (SPEC.md §12, corpus synthétique niveau 0) : générateur de monde, gabarits, contrôle des faits, graine fixe.

## 2026-10-15 — Phase 1 — Générateur de monde
- **Travail fait :** branche `phase-1` depuis `main`. `ccm/data/worldgen/monde.py` : `generer_monde(graine, reservoir, cfg, exclus)` rend un `Monde` (pydantic, gelé) : 6 à 20 personnes avec genre, prénom, nom, rôle, surnom éventuel ; 2 à 5 sociétés ; 3 à 8 lieux (communes ou adresses) ; 15 à 40 événements des 9 types de SPEC.md §12 avec date, heure, lieu, participants, sociétés, montants (`Decimal`), triés par date. Cas durs tirés par dossier : alias (un surnom), deux personnes de même nom de famille (prénoms différents), deux de même nom complet. Noms courants (`reservoirs.yaml`) ou inventés (syllabes + fins). Liste d'exclusion : `charger_exclusion(fichier)`, un nom complet par ligne ; tout « prénom nom » exclu est retiré. Config `configs/worldgen.yaml` + `WorldgenConfig`. Tests `tests/unit/test_worldgen.py` (invariants sur 600 mondes, octets identiques à graine égale, graine obligatoire, parts des cas durs, réservoirs disjoints, exclusion).
- **Mesures :** `make test` : 44 tests passés. 2 400 mondes en 2,8 s. Parts sur 2 400 dossiers : alias 0,293 ; même nom de famille 0,180 ; même nom complet 0,054.
- **Décisions :**
  - Cas durs tirés au hasard par dossier (Bernoulli), pas en quota exact : la part réelle varie de ±1 point autour de la cible. Hors cas durs, les noms de famille d'un monde sont deux à deux distincts, pour que les parts soient exactes à ce tirage près.
  - Réservoirs `entrainement` / `test` : une chaîne (prénom, nom, surnom, société, commune) appartient au réservoir donné par la parité du premier octet du SHA-256 de sa clé. Vaut pour les noms courants et inventés ; aucune liste à tenir à la main.
  - Clé de comparaison `cle()` locale (NFKC, minuscules, sans accents, tirets et espaces réduits) : sert à l'exclusion et aux réservoirs. La norme de l'anonymiseur (§6, avec retrait des titres) s'écrira en phase 2 dans `anonymize/`.
  - Le monde est défini dans `worldgen/monde.py`, pas dans `schema.py` : ce n'est pas un contrat d'échange (stock ou exemple), seulement la vérité terrain du générateur.
  - Rues sans nom de personne (« avenue Victor Hugo » serait un PER caché).
- **Écarts avec SPEC.md :** nouveau fichier `configs/worldgen.yaml` (absent de la liste de §3 ; règle « aucun paramètre en dur »). **La liste des personnes de Wikidata n'est pas encore téléchargée** : le générateur prend la liste en paramètre, les tests utilisent un petit fichier. Wikidata est sous CC0 ; il reste à choisir comment l'obtenir (environ 10 millions d'humains : requêtes SPARQL par tranches ou extraction d'un dump) et où la ranger (`runs/` ou hors dépôt). Versions contradictoires (30 %) pas faites : pas dans la tâche du soir.
- **Suite prévue :** question à Raphael sur la liste Wikidata (source, taille, langues des libellés). Puis versions contradictoires, formes d'un nom, gabarits des pièces (SPEC.md §12).

## 2026-10-15 — Phase 1 — Liste d'exclusion Wikidata
- **Travail fait :** `ccm/data/worldgen/wikidata.py` (proposition acceptée par Raphael : pas de dump, libellés français seulement, stockage laissé à l'agent). Requêtes SPARQL par lots de 500 sur query.wikidata.org : un nom est exclu s'il est le libellé ou l'alias français (`@fr`, correspondance exacte) d'un humain (Q5). Passe 1 : les 12 600 paires prénom courant × nom courant des réservoirs. Passe 2 : tous les « prénom nom » tirés pour le corpus (noms inventés compris), jusqu'à point fixe (un nom exclu est tiré de nouveau, le nouveau est vérifié). Fichiers dans le dépôt : `exclus_wikidata.txt` (noms exclus) et `verifies_wikidata.txt` (tous les noms vérifiés, 520 Ko). `configs/worldgen.yaml` : parties du corpus (`entrainement` 2 000 dossiers, graines 0 à 1 999 ; `validation` 200, graines 1 000 000 et suivantes ; `test` 200, graines 2 000 000 et suivantes, réservoir `test`), paramètres Wikidata. `mondes_corpus(cfg, exclus)`. Ligne Wikidata (CC0) dans `DATA_LICENSES.md`.
- **Mesures :** 36 847 noms vérifiés, 5 956 exclus : 5 894 paires courantes (47 %) et 62 noms du tirage avec une partie inventée (« Isabelle Rameau », « Brigitte Landeau », « David Rosier »…). Point fixe en 3 tours. Durée : quelques minutes. `make test` : 46 tests passés.
- **Décisions :**
  - Test hors ligne `test_corpus_hors_liste_wikidata` : les 2 400 mondes du corpus n'ont aucun nom exclu, et chacun de leurs noms est dans `verifies_wikidata.txt`. Il échoue si on change les réservoirs ou la config sans relancer le script (sonde : un nom du corpus retiré de la liste vérifiée fait échouer le test).
  - Validation : réservoir `entrainement`, graines à part. Test : réservoir `test`, graines à part (SPEC.md §12).
  - Seuls des noms tirés de nos réservoirs sont envoyés à Wikidata ; le générateur n'appelle jamais le réseau.
- **Écarts avec SPEC.md :** « liste des personnes de Wikidata » réduite aux libellés et alias français, en correspondance exacte sur nos noms (accord de Raphael). Un homonyme sous une autre graphie (sans accent, autre casse) ou seulement en anglais n'est pas vu.
- **Suite prévue :** versions contradictoires (30 % des dossiers), formes d'un nom, gabarits des pièces (SPEC.md §12).

## 2026-10-16 — Phase 1 — Pièces par gabarits, PDF natif, contrôle de provenance
- **Travail fait :** `ccm/data/worldgen/pieces.py` : `rediger_dossier(monde, cfg)` rend 8 à 25 pièces de 6 types (PV_AUDITION, PV_CONSTATATION, RAPPORT, COURRIER, CONTRAT, RELEVE) ; toujours un RAPPORT ; chaque événement dans une pièce au moins ; personne entendue jamais participante des faits qu'elle rapporte. Chaque ligne déclare ses faits (position, surface, entité ou valeur, forme du nom). `gabarits.yaml` : un jeu `entrainement` (entraînement et validation) et un jeu `test`, sans texte commun. Formes d'un nom (§12) : COMPLET, NOM_PRENOM, INITIALES, NOM_SEUL, TITRE_NOM (titre hors du fait), SURNOM, et « X, dit S » ; sociétés COMPLET ou COURT. Versions contradictoires : 30 % des dossiers, un événement dit par deux témoins (PV_AUDITION), le second change l'heure, un montant ou une personne ; vérité terrain dans `Dossier.conflit` et `Dossier.variante`. `controle.py` : contrôle de provenance. `pdf.py` : PDF natif (PyMuPDF, Helvetica intégrée en sous-ensemble, coupure aux espaces, tableau à filets pour les relevés). `corpus.py` et commande `ccm corpus` : `runs/corpus/niveau0/<partie>/<dossier>/Pnn.pdf`, `verite.json`, et `controle.json` (bilan). Tests `tests/unit/test_pieces.py`.
- **Mesures :** corpus complet : 2 400 dossiers, 39 231 pièces (entraînement 32 695, validation 3 269, test 3 267), 328 151 lignes, 684 066 faits, environ 1,2 Go, 2 min sur la machine locale. **Contrôle de provenance : 0 pièce rejetée (100 %).** Conflits : 608 / 2 000 en entraînement (0,304), 55 / 200 en validation, 72 / 200 en test. Avant correction, deux passes complètes ont donné la même empreinte SHA-256 de toute l'arborescence (même graine, mêmes octets) ; le test `test_corpus_memes_fichiers` le vérifie sur 4 dossiers à chaque `make test`. Premier passage : 2 pièces rejetées (majuscule de début de ligne appliquée au surnom « le Chat ») ; corrigé, test de régression. `make test` : 64 tests passés.
- **Décisions :**
  - Formulation = cadre (propre au type de pièce, 3 ou 4) × noyau (propre au type d'événement, 5 à 7). Au moins 5 noyaux sans second participant par type d'événement ; CONTRAT (parties, prix, lieu et date) et RELEVE (libellés) : 5 gabarits chacun. Le test compte aussi les formulations vues dans le corpus : au moins 5 par (type d'événement, type de pièce).
  - Le contrôle relit les surfaces avec ses propres analyseurs (montant, date, heure). Hors des faits : aucun chiffre, aucun mois, aucun mot d'un nom du monde, aucun mot à majuscule absent du texte fixe des gabarits. Le texte de chaque ligne doit se relire dans le PDF.
  - Une pièce par fichier PDF. Montants en « € » ou « euros », avec ou sans séparateur de milliers ; dates « 12 mars 2021 » ou « 12/03/2021 » ; heures « 14 h 30 », « 14h30 », « 14:30 ».
  - `verite.json` contient les noms : vérité terrain rangée dans `runs/`, hors de git ; ce n'est pas un fichier d'entraînement (les exemples passeront par l'anonymiseur).
  - Graine des pièces dérivée de celle du monde (`pieces-<graine>`) : le monde ne change pas.
- **Écarts avec SPEC.md :** un surnom en début de ligne garde sa minuscule (« le Chat a … ») : la surface d'un fait est toujours la forme exacte. Le type COURRIER n'a pas de motif d'en-tête dans §5 : l'ingestion le classera AUTRE tant que la table n'est pas complétée. **Licence :** PyMuPDF (choisi par §3) est sous AGPL ; à voir avec la licence de publication du code (§16).
- **Suite prévue :** questions par dossier (environ 40, sept types de §12) avec leur cible ; puis rapport de phase 1.

## 2026-10-17 — Phase 1 — Questions, vérité terrain et synthèse de référence
- **Travail fait :** `ccm/data/worldgen/questions.py` : `poser_questions(dossier, cfg)` rend environ 40 questions par dossier, des 7 types de SPEC.md §12. Chaque question : message (et historique pour un dialogue) avec ses faits déclarés ; étapes de justification dans l'ordre du raisonnement (rôle CITE, PREUVE ou CONFLIT ; chaque étape = lignes équivalentes, la première sert à la synthèse) ; vérité propre au type (`identites`, `calcul` en postfixe avec résultat exact, `declaration`, `ambigus` pour ASK_SAME, `abstention`) ; synthèse de référence (§10 bis) écrite depuis les faits des lignes citées : sources, éléments mots / pointeurs M et N vers les faits / CALCUL. `questions.yaml` : gabarits de questions et de synthèse, jeux `entrainement` et `test` sans texte commun ; 19 relations de synthèse (9 types d'événement, CIRCONSTANCES, ALIAS, RESSEMBLANCE, CONFLIT, SOMME, ECART, DUREE, MIN, MAX, DISTINCTS), 5 formulations chacune par jeu. `controler_questions` : lignes et faits existants, ancrage de chaque citation (§11), calcul refait, conflit lu dans les lignes, règles du masque de la synthèse (1 à 4 sources citées, pointeurs dans les sources, au plus 40 mots et 8 phrases, majuscule au seul premier mot, ni chiffre, ni nombre en lettres, ni mois ou jour, ni négation, ni sigle, ni prénom ou nom courant). `ccm corpus` écrit `questions.json` par dossier et compte questions, formulations et erreurs dans `controle.json`. Tests `tests/unit/test_questions.py` (10).
- **Correction des pièces :** 2 conflits sur l'heure sur 3 étaient invisibles (cadre sans `{H}` chez un témoin). Les deux témoins prennent maintenant un cadre avec l'heure ; test ajouté. Le corpus change (même graine, mêmes octets toujours vérifiés).
- **Mesures :** corpus complet en 1 min 53 s, 1,5 Go. Questions : entraînement 79 903, validation 7 987, test 7 989 ; **0 erreur de contrôle**, 0 pièce rejetée. Parts (entraînement) : fait simple 0,204 ; plusieurs étapes 0,254 ; identité 0,153 ; fait absent 0,102 ; **conflit 0,086** ; calcul 0,101 ; dialogue 0,102 (test : conflit 0,098). Chaque relation de synthèse : 5 formulations vues dans chaque partie. Identité avec preuve : 979 / 12 192 en entraînement. `make test` : 74 tests passés.
- **Décisions :**
  - Pas de suite d'actions de référence (phase 3, demande de Raphael) : la vérité terrain est structurée pour la construire (étapes ordonnées, faits pointés).
  - Références : ligne `P03:4`, fait `P03:4:1`. Une ligne = une proposition attendue de l'ingestion (phase 2 fera la correspondance).
  - Nom de la question = même clé que dans la ligne citée (et noms univoques dans le dossier), sauf identité et dialogue : aucune citation non ancrée hors de ces types. Une question sans nom (conflit désigné par le type et la date) est hors règle d'ancrage (§11).
  - Conflit : seuls les dossiers à versions contradictoires en ont ; 13 tentées par dossier, le reste va aux autres types. Les autres types n'utilisent jamais l'événement en conflit.
  - Identité avec preuve seulement entre surnom et nom complet (ligne « X, dit S ») ; sinon ressemblance (initiales, NOM Prénom, nom seul). La ligne de preuve compte parmi les justificatives.
  - Synthèse : 2 phrases par événement final (fait, circonstances), 1 par étape intermédiaire, plus une phrase d'identité, de conflit ou de calcul ; 2 à 5 phrases. Sans « un », « une » (nombres en lettres possibles dans V). Abstention et ASK_SAME : sans synthèse.
- **Écarts avec SPEC.md :** part des conflits 0,086 au lieu de 0,10 en entraînement (un seul événement contredit par dossier : environ 11 questions distinctes possibles). La liste V n'existe pas encore (phase 5) : le contrôle des mots est une liste de mots refusés, à refaire contre V. Une question dont la version contradictoire nomme les témoins seulement par initiales n'a de conflit que par la date.
- **Décisions de Raphael (même jour) :** 8,6 % de conflits acceptés. La ligne de preuve d'un SAME est citée : elle peut être source d'une phrase de synthèse (choix déjà appliqué).
- **Questions pour Raphael :** la preuve d'un SAME (le P de `SAME M M P`) compte-t-elle comme citée pour servir de source à une phrase de synthèse ? Accepter 8,6 % de conflits, ou ajouter un second événement contredit dans les dossiers à conflit ?
- **Suite prévue :** rapport de phase 1 (`reports/phase-1.md`) et relecture avec Raphael avant l'étiquette `phase-1-ok`.

## 2026-10-18 — Phase 1 — Corpus 2 000 / 200 / 200 et séparation
- **Travail fait :** génération du corpus complet (`ccm corpus`) : entraînement 2 000 dossiers (graines 0 à 1 999, réservoir et gabarits `entrainement`), validation 200 (graines 1 000 000 à 1 000 199, réservoir et gabarits `entrainement`), test 200 (graines 2 000 000 à 2 000 199, réservoir et gabarits `test`, pièces et questions). Audit de la séparation : **deux fuites trouvées et corrigées** dans `monde.py` : la rue d'une adresse et la racine d'un nom de société (« SAS Picard ») étaient tirées sans filtre de réservoir (seul le nom entier l'était) ; une chaîne d'entraînement pouvait donc paraître dans le test. `noms_du_monde(m)` liste toutes les chaînes de nom (prénoms, noms, surnoms, sociétés et racines, communes, rues) ; l'invariant des mondes les contrôle toutes (sonde : l'ancien code échoue sur « Nasier », « Picard »). `controle.json` a une clé `separation` : graines et identifiants de dossier communs entre deux parties, clés de nom communes entre le test et les autres ; `ccm corpus` échoue si elle n'est pas vide. Test `test_separation_des_parties`.
- **Mesures :** 2 400 dossiers, 39 231 pièces (32 695 / 3 269 / 3 267), 0 pièce rejetée ; questions 79 953 / 8 000 / 7 982, 0 erreur de contrôle. **Séparation : aucun recouvrement** (graines, dossiers, chaînes de nom). Conflits : 623 / 2 000 dossiers en entraînement (part des questions 0,087), 62 / 200 en validation, 70 / 200 en test (0,092). Toujours 5 formulations par relation de synthèse dans chaque partie. 1 min 53 s, 1,45 Go ; deux passes : même empreinte SHA-256 (`b4361598…`). `make test` : 75 tests passés.
- **Décisions :**
  - La validation garde le réservoir et les gabarits d'entraînement (SPEC.md §12 demande des gabarits différents pour le test seulement) ; ses graines sont à part.
  - Mots génériques des noms de société (formes SARL, SAS… et activités « Transports », « Conseil »…) et numéros de rue communs aux deux réservoirs : ce ne sont pas des noms.
  - Les personnes ne changent pas (tirées avant les sociétés) : la liste Wikidata reste valable sans nouvelle requête (`test_corpus_hors_liste_wikidata` passe). Sociétés, lieux, pièces et questions changent.
- **Écarts avec SPEC.md :** aucun nouveau.
- **Suite prévue :** rapport de phase 1 (`reports/phase-1.md`) et relecture avec Raphael avant l'étiquette `phase-1-ok`.

## 2026-10-18 — Phase 1 — Rapport de phase, licence PyMuPDF
- **Travail fait :** `reports/phase-1.md` (seuils, écarts, risques, questions). Clone neuf de `phase-1` : `make setup && make test` OK (75 tests) ; CI verte.
- **Mesures :** les deux seuils de phase 1 sont atteints (contrôle à 100 %, même graine, mêmes fichiers).
- **Décisions (Raphael) :** §16 « Publication » : **code fermé, modèle à poids ouverts**. Conséquence : PyMuPDF (AGPL) reste seulement dans `worldgen` (outil interne, non distribué ; l'AGPL ne couvre pas les PDF ni la vérité terrain produits). L'ingestion de la phase 2 se fera avec une bibliothèque sans copyleft (pdfplumber, MIT, ou pypdfium2, Apache/BSD) ; PyMuPDF passera dans un groupe de dépendances interne. Changement de SPEC.md §3 et §5 (« PyMuPDF », `find_tables()`) validé, à faire au début de la phase 2.
- **Écarts avec SPEC.md :** §3 et §5 nomment encore PyMuPDF (changement validé, pas encore écrit).
- **Suite prévue :** réponses de Raphael aux questions 2 à 4 de `reports/phase-1.md` (motif COURRIER, §16 budget et enseignant, accord pour `phase-1-ok` et la fusion dans `main`).

## 2026-10-18 — Phase 1 — Relecture, fin de phase
- **Travail fait :** relecture de `reports/phase-1.md` avec Raphael ; réponses écrites au rapport. Étiquette `phase-1-ok`, fusion de `phase-1` dans `main` (accord de Raphael).
- **Mesures :** aucune nouvelle (seuils atteints, voir l'entrée précédente).
- **Décisions (Raphael) :**
  - §16 « Budget de calcul » : RTX 3090, **aucun plafond d'heures** ; l'entraînement sera étalé sur plusieurs jours (éviter l'effondrement de représentation). Le cas d'arrêt 4 (§15) garde sa limite de 5 jours par durée mesurée.
  - §16 « Modèle enseignant » : **Mistral, local** (Raphael, après avoir d'abord choisi Qwen : meilleur en français). Licences lues sur Hugging Face le 2026-10-18 : Mistral-7B-Instruct-v0.3, Mistral-Nemo-Instruct-2407 (12B) et Mistral-Small-3.1-24B-Instruct-2503 sous Apache 2.0 ; Ministral-8B-Instruct-2410 sous licence propre, écarté. Modèle exact à choisir en phase 4 parmi les modèles Apache 2.0 (Nemo 12B ou Small 3.1 24B quantifié tiennent sur la RTX 3090) ; il s'écrira dans `DATA_LICENSES.md` au téléchargement.
  - COURRIER : motif d'en-tête à choisir sur de vrais dossiers ; pas de changement de §5 pour l'instant.
- **Écarts avec SPEC.md :** §3 et §5 nomment encore PyMuPDF (changement validé, à faire en phase 2).
- **Suite prévue :** phase 2 (SPEC.md §5, §6, §7) : branche `phase-2` ; d'abord SPEC.md §3 et §5 avec la bibliothèque d'ingestion sans copyleft (pdfplumber ou pypdfium2, à mesurer sur le niveau 0), puis extraction.

## 2026-10-19 — Phase 2 — Ingestion, étapes 1 à 3 bis
- **Travail fait :** branche `phase-2` depuis `main`. SPEC.md §3 et §5 mis à jour (changement validé le 2026-10-18) : extraction par **pypdfium2** (Apache 2.0 / BSD, choix de Raphael ce soir à la place de PyMuPDF que nommait la tâche) ; PyMuPDF passe dans le groupe de dépendances `interne` (worldgen et tests), figé `<2`. `ccm/ingest/extract.py` (étape 1 : mots et boîtes de police de pdfium ; OCR Tesseract `fra` si moins de 20 caractères natifs, image 300 dpi en PGM sur l'entrée de `tesseract`, sortie TSV, confiance par mot ; coupe XY en colonnes et bandes, lignes, paragraphes ; recollage des lignes, des mots coupés et des paragraphes coupés par un saut de page). `ccm/ingest/piece_type.py` (étape 2). `ccm/ingest/segment.py` (étapes 3 et 3 bis : pysbd, abréviations et initiales masquées, DEPEND_DE, SUIVANTE, PARTIE). `ccm/graph/store.py`, `ccm/ingest/pipeline.py`, commande `ccm ingest SOURCES --stock BASE`. `configs/ingest.yaml` : tous les paramètres. Tesseract 5.4.0 installé (winget) et `fra.traineddata` dans `runs/modeles/tessdata/` ; licences dans `DATA_LICENSES.md`. CI Ubuntu : paquets `tesseract-ocr-fra`. Tests `tests/unit/test_ingest.py` (11).
- **Mesures :** les 200 dossiers de validation ingérés (3 269 pièces, 1 min 51 s, un stock par dossier dans `runs/ingest/niveau0/validation/`). **26 288 / 26 288 lignes hors tableau** (phrases, champs, en-têtes) retrouvées chacune comme une proposition au texte exact ; 965 propositions en plus = les 965 lignes de tableau (étape 4, pas encore faite : cellules lues ligne par ligne, texte mélangé). 0 fichier coupé à tort en deux pièces. Types : 100 % justes sauf COURRIER → AUTRE (571, aucun motif dans §5). EN_TETE : 2 698 / 3 269 (les 571 manquants sont les en-têtes de courrier). Arêtes : 23 984 SUIVANTE, 5 044 DEPEND_DE ; aucune PARTIE (phrase la plus longue : 41 mots). OCR : 5 pièces de validation rendues en image à 200 dpi : 32 / 33 lignes exactes, confiance moyenne 0,91, environ 2 s par page. `make test` : 86 tests passés.
- **Décisions :**
  - Boîtes « larges » de pdfium (hauteur de police, uniforme) pour le texte natif : nouveau paragraphe si l'écart entre deux lignes dépasse 0,2 × la hauteur médiane des lignes ; OCR (boîtes serrées) : 0,65, réglé sur des pages de validation rendues en image.
  - Colonnes : coupe à une gouttière d'au moins 15 pt si les deux côtés font au moins 150 pt (les colonnes de tableau, plus étroites, ne sont pas des colonnes de texte). Bandes : écart de 1,5 × la hauteur médiane des mots.
  - Saut de page : la dernière ligne d'une page continue sur la suivante si le premier mot de la suivante ne tenait pas dans la place restante (critère de coupure de ligne).
  - Trait d'union en fin de ligne : la ligne suivante est recollée sans espace ; le trait tombe devant une minuscule, reste devant une majuscule (« Import-Export »). pdfium rend ce trait par U+FFFE, remis en « - ».
  - Pièces : motifs d'en-tête sensibles à la casse ; table ordonnée du plus précis au plus général (PV d'audition, PV de constat, rapport, contrat, relevé, réquisition et PV sans précision → AUTRE, article de loi → LOI). Rang : LOI 1, le reste 0 (les types circulaire, doctrine, pédagogique n'existent pas encore dans `TypePiece`). EN_TETE : paragraphe des 15 premières lignes de la première page, avec un motif et sans minuscule.
  - Segmentation : points des abréviations de la liste et des initiales (« É.M. », « P.V. ») masqués avant pysbd, texte inchangé. DEPEND_DE va de la phrase vers la précédente (même pièce) ; question-réponse d'audition : la phrase suit une ligne « Question : » ou une phrase finie par « ? », ou commence par « Réponse : ». PARTIE : coupe après « ; » et « : », DEPEND_DE dans les deux sens entre parties voisines ; la dépendance de la phrase part de sa première partie.
  - SUIVANTE entre deux propositions qui se suivent dans une pièce. Page d'une proposition : page du fichier où elle commence. `ocr_conf` = moyenne des confiances des mots de la proposition (1,0 en natif) ; `ocr_bas` (< 0,85) se lit sur `ocr_conf`, pas de colonne.
  - Identifiant : nom du fichier sans extension, puis `<nom>.2`, `<nom>.3` pour les pièces suivantes d'un même fichier. Un fichier déjà ingéré (même SHA-256) est ignoré ; chaque pièce ajoutée augmente la révision de 1.
  - Test de propriété de la config : l'aller-retour se fait sur la vraie config d'ingestion (la classe a maintenant des champs obligatoires).
- **Écarts avec SPEC.md :** COURRIER jamais reconnu (motif en attente, décision du 2026-10-18). Limite 128 jetons non appliquée : 80 mots tant que le tokenizer n'existe pas (valeur de §5). La coupe XY peut mélanger deux colonnes dont les paragraphes ne s'alignent pas sous un titre pleine largeur (non mesuré : niveau 0 à une colonne). En cherchant les titres des gabarits, j'ai vu ceux du jeu de test dans `gabarits.yaml` : les motifs n'ont été réglés que sur la validation (ajout de « PROCÈS-VERBAL DE CONSTAT », vu dans 302 pièces de validation) ; aucun titre propre au test n'a été ajouté.
- **Suite prévue :** étape 4 (SPEC.md §5) : tableaux et champs « Libellé : valeur » ; choix de la bibliothèque de détection des tableaux sans copyleft.

## 2026-10-20 — Phase 2 — Ingestion, étapes 4, 6 et 7
- **Travail fait :** étape 4 dans `ccm/ingest/extract.py` et `segment.py` : cellules = rectangles tracés de la page (objets chemin de pypdfium2) ; rectangles de même ordonnée et même hauteur = une rangée (au moins 2 cellules) ; la rangée entre dans la coupe XY comme un seul mot, puis devient une proposition LIGNE_TABLEAU « cellule | cellule | … » ; la première rangée d'un tableau en est l'en-tête, les autres reçoivent DEPEND_DE vers elle (même sur la page suivante). Paragraphe « Libellé : valeur » (libellé de 2 à 40 caractères) = une proposition CHAMP. Étape 6 : `ccm/ingest/numbers.py`, table `nombre`. Étape 7 : `ccm/ingest/dedup.py` (SHA-1 du texte normalisé, MinHash 128 permutations sur les triplets de mots, LSH, seuil 0,9), recalculé sur tout le stock après les fichiers (`ingerer_fichiers`, commande `ccm ingest`). Dépendance `datasketch` 2.0.0 (MIT). SPEC.md §5, étape 4 : bibliothèque choisie écrite (pypdfium2). 34 tests ajoutés (`tests/unit/test_ingest_tableaux_nombres_doublons.py`) ; le test du dossier synthétique contrôle aussi les genres et les nombres.
- **Mesures (200 dossiers de validation, 25 s sur 8 processus) :** 27 253 / 27 253 lignes de la vérité retrouvées chacune comme une proposition au texte exact (tableaux compris). LIGNE_TABLEAU : 965 / 965 avec le bon genre ; 260 tableaux, 705 arêtes DEPEND_DE vers l'en-tête (= 965 − 260). CHAMP : 5 447 / 5 447, 0 faux positif. EN_TETE : 2 698 / 3 269 (inchangé : en-têtes de courrier). Nombres, dates, heures déclarés : 21 722 / 21 722 lus avec la bonne valeur ; 2 962 nombres de plus, tous des numéros de voie (« 77 rue de la Fontaine ») dans des adresses, qui sont des mentions LIEU de l'étape 5. Aucune référence (2025/40649…) lue comme nombre. Doublons : 2 268 groupes, 4 028 arêtes DOUBLON_DE ; 1 seul groupe de quasi-copies (« euros » / « € ») ; le reste = formules répétées d'une pièce à l'autre (« Lecture faite, persiste et signe. », titres, « Maître, »). `make test` : 120 tests passés.
- **Décisions :**
  - Tableaux : pas de bibliothèque en plus (pdfplumber écarté : deuxième lecteur de PDF). Seuls les tableaux à cellules tracées en rectangles sont lus ; un tableau à filets seuls, sans cadre, ou en image (OCR) ne l'est pas. Le seuil de paragraphe et la hauteur médiane des mots ignorent les rangées (sinon les rangées hautes d'un relevé fusionnaient en-tête et champs : 44 champs perdus au premier essai).
  - Champ : paragraphe entier, non découpé en phrases. « Question : … » et « Réponse : … » d'audition ne sont pas des champs (le test question-réponse cassait).
  - Nombres : ordre des motifs références → dates → heures → chiffres avec unité → lettres avec unité → année seule → chiffres sans unité (unité vide) ; une position prise ne sert plus. Unités et formes, références, mois, nombres en lettres dans `configs/ingest.yaml`. Valeurs : décimal exact (texte de `Decimal`, « 1250.00 »), date ISO (« 2024-12-07 », « 2024-12 », « 2024 »), heure du jour en minutes depuis minuit (« 21h59 » → 1319). Unité « date » pour une DATE (comme l'exemple de §4). « N heure(s) » est une durée, sauf après « à », « vers », « dès », « jusqu'à » ; « 21 h », « 21h59 », « 21:59 » sont des heures du jour. Date impossible (31/02) : rien. Date sans année (« le 7 décembre ») : rien.
  - `nombres()` reçoit les zones exclues (mentions de l'étape 5, dont les adresses) ; vide en attendant l'étape 5.
  - Doublons : normalisation NFKC, minuscules, blancs réduits ; moins de 3 mots : copies exactes seulement ; Jaccard exact des triplets contrôlé après le LSH ; version gardée = meilleure `ocr_conf`, à égalité la première ingérée ; `groupe_doublon` = prop_id de la version gardée (NULL hors groupe) ; DOUBLON_DE de chaque autre copie vers elle. La révision ne change pas (aucune pièce ajoutée).
- **Écarts avec SPEC.md :** les formules répétées (« Lecture faite, persiste et signe. ») deviennent des doublons entre pièces : conforme à §5, mais la recherche les ignorera dans toutes les pièces sauf une ; à revoir si une citation de formule doit garder sa pièce. Un « Il déclare : … » court serait lu comme CHAMP (aucun cas au niveau 0). Les références ne sont pas encore écrites dans `mention` (type REF, étape 5) : l'étape 6 les écarte seulement.
- **Suite prévue :** étape 5 (SPEC.md §5, §6) : détection des noms (union GLiNER, spaCy, règles), mentions et zones exclues des nombres ; licences des modèles à vérifier au téléchargement.

## 2026-10-21 — Phase 2 — Conflits (étape 8), `ccm forget` et T8
- **Travail fait :** tâche donnée par Raphael ce soir (à la place de la « suite prévue », l'étape 5). `ccm/ingest/conflicts.py` (étape 8, règle de §5 telle quelle) : signature (noms → type, nombres → `NUM:unité`, dates → `DATE`, racines des autres mots) rangée dans `proposition.signature` ; candidats par MinHash LSH puis Jaccard exact ≥ 0,6 ; inclusion des normes de noms ; comparaison des valeurs alignées par unité et par ordre ; négation si Jaccard ≥ 0,8. Appelée après les doublons dans `ingerer_fichiers`. `ccm/ingest/racines.py` (minuscules, mots vides Snowball, racines PyStemmer, accents retirés), partagé avec `ccm/search/bm25.py` (index BM25 du stock dans `<base>.bm25/`, versions gardées seulement, `prop_ids.json`, pas de texte copié ; construit par `ccm ingest`). `ccm/anonymize/names.py` : norme d'un nom (§6). `ccm/graph/oubli.py` et commande `ccm forget NOMS --stock BASE`. `ajouter_mentions` dans `graph/store.py`. Mesure : `uv run python -m ccm.eval.conflits runs/corpus/niveau0/validation runs/conflits/validation`. Dépendances : `bm25s` 0.3.14 (MIT), `PyStemmer` 3.1.0 (MIT/BSD). Tests : `tests/unit/test_conflits_oubli.py` (6, dont T8).
- **Mesures (200 dossiers de validation, 62 à versions contradictoires, 137 paires de référence, 30 s sur 8 processus) :**
  - Paires de référence : une ligne de l'événement en conflit dans la version du monde et une dans la version contradictoire, portant toutes deux le champ changé avec des valeurs différentes (règle du contrôle des questions CONFLIT).
  - Essai 1, règle de §5, sans mentions (table vide, ingestion d'aujourd'hui) : 25 VP, 6 200 FP, **précision 0,004**, rappel 0,18 (HEURE 19/62, MONTANT 6/19, PERSONNE 0/56).
  - Essai 1 bis, règle de §5, mentions de référence (faits PER/ORG/LIEU/REF de la vérité, nombres dans une mention retirés) : 2 VP, 5 807 FP, **précision 0,0003**, rappel 0,015.
  - Essai 2, seuil de Jaccard (seul réglage permis) : à 0,7, 0,8, 0,9 et 1,0 : 0 VP, 5 772 à 5 739 FP. Les faux positifs ont un Jaccard de 1 : relever le seuil n'y fait rien.
  - Essai 3, variantes de règle mesurées sur les paires prédites, **non appliquées** : au moins 3 racines dans chaque signature : 2 VP / 140 FP ; dates alignées égales exigées : 2 / 26 ; les deux : 2 / 12 (précision 0,14).
  - Faux positifs (mentions de référence) : 5 188 paires de CHAMP courts (« Date : 13 mars 2025 » / « Date : 22 juillet 2025 ») ; le reste, des phrases d'un même gabarit sur deux événements distincts (« Le 29 avril 2024, nous rapportons les constatations suivantes : »). Dans les deux cas, une date différente veut dire un autre fait, pas un conflit.
  - Manques : sur 137 paires, 98 ont un Jaccard < 0,6 (le second témoin parle avec un autre gabarit : « un vol portant sur … a été commis par » / « ont pris … dans la caisse ») et 124 échouent à l'inclusion des normes (« Damien Neldoret » / « NELDORET Damien », « CARON Valtalien » / « Caron » : normes différentes). Le champ PERSONNE ne peut pas être trouvé par la règle (nom changé = noms non inclus).
  - T8 : passe (base, fichier brut, index, pas de journal laissé). `make test` : 126 tests passés.
- **Décisions :**
  - Arête CONFLIT écrite dans les deux sens. Seules les versions gardées des doublons entrent dans la détection. Deux dates dont l'une est un préfixe de l'autre (« 2024-12 » / « 2024-12-07 ») ne sont pas différentes. Les noms sont comparés avec leur type ; toutes les mentions comptent (REF compris).
  - Mots vides : liste française de Snowball (« on » entre guillemets dans le YAML, sinon booléen). Le mot « a » n'y est pas.
  - Norme : titres retirés en tête (liste `noms.titres` de `configs/ingest.yaml`), sauf s'il ne reste qu'un mot.
  - `ccm forget` : caviardage par « █ », un par caractère (positions des autres mentions et des nombres inchangées) ; aussi toute autre occurrence, sans casse, des surfaces et des normes oubliées (propagation de §6) ; mentions touchées par un caviardage supprimées ; contraintes qui nomment une norme supprimées ; mêmes chaînes caviardées dans `piece.chemin` et les textes de `trace`. Pièces touchées : révision max + 1. Doublons, signatures, conflits recalculés, `VACUUM`, index BM25 reconstruit.
  - L'index BM25 (§7, première ligne seulement) est écrit ce soir parce que `forget` doit le reconstruire et T8 le contrôler ; le reste de la recherche n'est pas commencé.
- **Écarts avec SPEC.md :** cible de précision des conflits (0,9) **non atteinte** : 0,0003 à 0,004 avec la règle de §5, après trois essais documentés ; ce n'est pas un seuil de phase, mais aucun réglage permis ne l'approche, et changer la règle est une décision de Raphael. La règle est gardée telle quelle dans le code. Conséquence : un stock de validation a environ 29 arêtes CONFLIT fausses par dossier ; la recherche (§7, saut par CONFLIT) et le rendu (§11, bloc CONFLIT) en seraient pollués. Limites de `forget` : un nom présent dans `piece_id` (nom de fichier) n'est pas caviardé ; les octets d'un fichier supprimé (journal SQLite, ancien index) restent sur le disque tant que le système de fichiers ne les réécrit pas. Les mentions de T8 sont posées à la main (étape 5 pas faite).
- **Questions pour Raphael :**
  1. Règle des conflits : (a) une date alignée différente = un autre fait, pas un conflit ; (b) au moins N racines par signature ; (c) inclusion des noms sur les mots des normes (« neldoret damien » ⊂ …) ; (d) garder la règle de §5 et n'écrire les arêtes qu'au-dessus d'une précision mesurée ; (e) trancher le point « Conflits reformulés » de §16 (encodeur de phrases non génératif). Même avec (a) + (b), la précision mesurée est 0,14 et le rappel ne bouge pas.
  2. Le générateur fait dire la version contradictoire avec un autre gabarit que la version du monde : est-ce voulu (cas de la limite écrite) ? Sinon, la mesure du rappel de §5 n'a presque rien à trouver.
- **Suite de la séance (échange avec Raphael) :** la précision de 0,9 devient une condition de passage. Règle « même fait » mesurée par un script hors du dépôt (pièces différentes, même jour, nom de famille commun) : heure différente avec lieu compatible 59 VP / 10 FP ; montants en recouvrement partiel 4 / 0 (après comparaison en décimal exact : « 45 104 » et « 45 104,00 » étaient lus comme deux valeurs, défaut à corriger dans `conflicts.py`) ; négation cherchée hors des noms 0 FP (« Hugo Non ») ; personne différente 2 / 32. Ensemble : 63 VP / 10 FP, précision 0,86, rappel 63 / 137. Raphael : l'usage principal sera les lois, où les conflits sont surtout logiques. Proposition écrite dans `reports/proposition-conflits.md` : conflits établis par le code (même fait ; versions d'un article), avec garantie et seuil 0,9, et conflits supposés par le modèle (`CONFLIT SANS_PREUVE`, lexique inchangé), affichés comme hypothèse. SPEC.md non modifié.
- **Décision de Raphael :** proposition validée (deux niveaux, `CONFLIT SANS_PREUVE`, lexique inchangé) ; rappel minimal au choix de l'agent ; types d'acte en valeur de départ, à reprendre sur de vraies données ; versions d'articles dès la phase 2 (source et version servent au lecteur pour choisir). Consigne : attention au surajustement, et écrire précisément quel conflit est repéré (le même fait à deux ou trois dates peut être une répétition comme un problème d'alibi ou de témoin).
- **Travail fait (suite) :** SPEC.md mis à jour (§2 seuil de phase 2 : précision ≥ 0,9 et rappel ≥ 0,5 sur heure et montant, réglage sur la validation, mesure finale une fois sur le test ; §5 réécrit, avec la limite écrite des dates différentes ; §10, §11, §12, §14, §16) ; PLAN.md. `ccm/ingest/conflicts.py` réécrit : cas A (même fait : pièces différentes, jour commun, nom de famille PER ou norme ORG commun, lieu et type d'acte compatibles ; conflit si heures alignées différentes, montants en euros en recouvrement partiel, ou négation dans une seule, hors des mentions ; valeurs en décimal exact) et cas B (versions d'un article : clé code + numéro, référence exclue du texte comparé). Plus de signature ni de MinHash : la colonne `proposition.signature` reste vide (§5 ne la définit plus). `nom_famille` dans `ccm/anonymize/names.py` (§6). Config : `noms.particules`, `conflits.actes` (10 types, vocabulaire pénal courant écrit sans partir des gabarits ; écartés pour collision de racine : arrêt, arrêté, rendez, coup, communication), `motif_article`, `motif_code`. `ccm/eval/conflits.py` : rappel heure + montant, tranche de dossiers. Tests réécrits (16 dans `test_conflits_oubli.py`).
- **Mesures (suite), mentions de référence :**
  - Validation (200 dossiers, réglage) : 65 VP, 1 FP, **précision 0,985** ; rappel heure + montant **0,80** (HEURE 60/62, MONTANT 5/19) ; PERSONNE 0/56 (hors niveau 1 par décision).
  - Contrôle de surajustement, entraînement jamais regardé pendant le réglage : dossiers 0 à 199 : 45 VP, 4 FP, **0,918**, rappel heure + montant 0,94 ; dossiers 200 à 599 : 102 VP, 4 FP, **0,962**, rappel 0,85. Ensemble (600 dossiers) : 147 VP, 8 FP, 0,948. Aucun réglage fait après avoir vu les faux positifs de l'entraînement (deux actes différents le même jour, dont l'un n'a pas de type d'acte lu : « ont pris … dans la caisse », « déclarations recueillies »).
  - Sans mentions (ingestion d'aujourd'hui) : 0 arête ; le cas A attend l'étape 5.
  - Cas B : pas de texte de loi au niveau 0 ; tests unitaires seulement.
  - `make test` : 136 tests passés.
- **Écarts avec SPEC.md (suite) :** aucun. Risques : la marge au-dessus de 0,9 est mince sur l'entraînement (0,918 sur 200 dossiers) ; les validation et entraînement partagent leurs gabarits, le vrai contrôle sera le test (gabarits propres), une seule fois en fin de phase. Rappel MONTANT faible (5/19) : la règle du recouvrement partiel ne voit pas un montant seul changé ; voulu (sinon 583 FP). La liste des types d'acte vient du vocabulaire pénal courant ; un fait sans mot de la liste est compatible avec tout acte, source des faux positifs restants.
- **Suite prévue :** étape 5 (SPEC.md §5, §6) : détection des noms (union GLiNER, spaCy, règles), mentions et zones exclues des nombres ; licences des modèles à vérifier au téléchargement.

## 2026-10-22 — Phase 2 — Étape 5 : détection des noms
- **Travail fait :** `ccm/ner/` : `detectors.py` (D1 GLiNER `gliner_multi-v2.1`, seuil 0,3, étiquettes person/organization/location/address/product ; D2 spaCy `fr_core_news_lg`, PER/ORG/LOC/MISC ; D3 règles REF = `nombres.references` + courriel, URL, SIREN/SIRET après mot-clé, dossier ; D4 majuscules, lexiques Hunspell fr + en lus par `spylls`), `union.py` (union, limites, `detecter`), `propagate.py` (propagation dans la base, messages de l'utilisateur sans casse ni accents). Pipeline : étape 5 avant l'étape 6 (les nombres sont lus hors des zones de noms) ; propagation recalculée sur tout le stock après les fichiers, avec retrait des nombres recouverts. `ccm modeles` (`ccm/data/modeles.py`) télécharge les modèles dans `runs/modeles/` (révisions et SHA-256 figés) ; `make setup` l'appelle ; CI : cache de `runs/modeles`. torch 2.14.1 CUDA 12.6 sous Windows (GTX 1660 Ti), CPU sous Linux. `ccm/eval/noms.py` : rappel par type sur le corpus. `ccm/eval/conflits.py` : mesure avec les mentions détectées. Licences dans `DATA_LICENSES.md`. Tests : `test_noms.py` (9), T7 étendu à `ccm.ner` et au chargement des modèles réseau coupé.
- **Mesures (validation, 200 dossiers, 34 619 mentions de référence ; « masquée » = chaque mot de la mention est dans une zone détectée, de tout type) :**
  - Essai 1 (union, limites, propagation) : rappel PER **0,999** (22 042), ORG 0,9995 (4 322), LIEU 1,0 (4 986), REF 1,0 (3 269). Nombres de référence recouverts par un nom : 76 / 21 722 (zones à cheval sur une cellule « Société X | 38 532,65 € », ou sur une date voisine).
  - Essai 2 (zone coupée aux « | », mots sans lettre retirés des bords) : PER **0,999**, ORG 0,9995, LIEU 0,9914, REF 1,0 ; nombres recouverts 4 / 21 722. Limites exactes : PER 0,93, ORG 0,85, LIEU 0,40 (adresse coupée à la virgule), REF 0,31 (« n° 2025/… » plus large que la référence). Bon type : PER 0,98, ORG 0,62 (souvent PER par priorité), LIEU 0,94. Zones détectées 45 147, dont 8 059 sans aucune mention de référence (précision des zones 0,82) : « Je », « Nous », « Date », « Fait », en-têtes « PROCÈS-VERBAL D'AUDITION », « P.V. » ; la propagation les répand dans la base.
  - Manques PER : surnoms à article (« le Belge », « le Marseillais », « le Prof », « le Chat ») : mot courant du lexique, vu par aucun modèle. Manques LIEU de l'essai 2 : « 103 rue de la Poste, … » typé ORG (« La Poste »), numéro retiré du bord.
  - Essai 3 (un numéro en tête reste dans la zone s'il est suivi d'un mot en minuscules autre qu'un mois) : tests unitaires seulement ; **pas mesuré** sur la validation (voir arrêt ci-dessous).
  - Seuil de phase 2 sur les noms (rappel PER ≥ 0,98) : **atteint** (0,999), sur la validation ; mesure finale sur le test en fin de phase.
  - Contrôle de surajustement (entraînement 0 à 99) et conflits avec mentions détectées : **non faits**, la tâche a été arrêtée par Claude Code (mémoire de la machine basse avec 3 processus × GLiNER + spaCy). Non relancée sans accord de Raphael.
  - `make test` : 147 tests passés.
- **Décisions :**
  - Rappel : une mention compte comme masquée si chacun de ses mots (`\w+`) est dans une zone de nom, de tout type ; la ponctuation ou une virgule entre deux zones ne révèle rien. L'exactitude des limites et du type est mesurée à part.
  - Union : deux zones qui se chevauchent donnent la zone qui couvre les deux (« la zone la plus longue » lue comme leur réunion, pour ne rien laisser à découvert), type le plus prioritaire.
  - Limites : deux zones séparées par des blancs ou des particules (« de », « de la », « d' »…) fusionnent ; titres en tête retirés, zone réduite à un titre supprimée ; une zone ne franchit jamais « | » ; mots sans lettre (et mois) retirés des bords, sauf numéro de rue ; zone de nom sans majuscule supprimée (montants lus MISC). D4 regroupe les mots voisins séparés par des blancs ; jeux d'initiales « S.M. » trouvés par motif.
  - Propagation : chaîne exacte d'au moins 2 caractères, entre limites de mot ; une zone existante est gardée si son type est au moins aussi prioritaire, sinon le type connu l'emporte (un nom PER vu AUTRE par D4 ailleurs redevient PER). Message de l'utilisateur : normes connues cherchées sans casse ni accents, tirets et blancs égaux.
  - Lexique de D4 : dictionnaires Hunspell (Dicollecte fr 7.7 MPL 2.0, SCOWL en_US) ; mot courant si sa forme en minuscules est reconnue. **Lexique 3.83 écarté** : licence CC BY-NC 4.0 (usage commercial non tranché).
  - transformers < 5 (le tokenizer de mDeBERTa ne se charge pas en 5.16) ; `protobuf` ajouté.
  - T8 : mentions détectées effacées avant de poser les mentions à la main (le test reste indépendant des détecteurs ; résultat attendu inchangé).
- **Écarts avec SPEC.md :** mesure sur WikiNER et TAB non faite (corpus synthétique seulement). Les 24 relations, les slots et la commande `anonymize` ne sont pas commencés. Licence spaCy LGPL-LR : sans obligation tant que le modèle n'est pas redistribué ; à revoir si la chaîne est distribuée avec lui.
- **Questions pour Raphael :**
  1. Faux positifs (précision des zones 0,82) : « Je », « Nous », en-têtes de PV masqués, puis propagés. Ils ne touchent pas le seuil, mais ils risquent de nuire aux conflits (nom de famille commun « je ») et à la lecture du modèle. Faut-il relever le seuil de GLiNER, ou ne pas propager une chaîne qui est un mot courant du lexique ? À mesurer avant de décider.
  2. Relancer les mesures avec 2 processus au lieu de 3 (mémoire) ?
- **Suite prévue :** avec accord, relancer la validation (essai 3), le contrôle sur l'entraînement 0 à 99 et la mesure des conflits avec les mentions détectées (`ccm.eval.conflits`, processus=2) ; puis étape suivante de la phase 2 (relations et slots, SPEC.md §6).

## 2026-10-22 — Phase 2 — Faux positifs des noms : deux pistes mesurées
- **Travail fait :** à la demande de Raphael, mesure sur la validation (200 dossiers, un seul processus) de deux pistes contre les faux positifs : seuil de GLiNER (0,3 à 0,8) et propagation interdite aux chaînes dont tous les mots sont courants (lexiques de D4 ; la chaîne reste masquée là où elle est détectée). Détecteurs lancés une fois (scores de GLiNER gardés), variantes rejouées sur les textes des lignes ; script hors du dépôt. Mesures relancées : non (décision de Raphael).
- **Mesures (rappel PER / ORG / LIEU ; précision des zones) :**
  - Code actuel (seuil 0,3, sans filtre ; inclut l'essai 3) : 0,999 / 0,9995 / **1,0** ; 0,822. L'essai 3 rend le LIEU à 1,0 (0,9914 à l'essai 2).
  - Seuil seul : 0,4 → 0,999 / 0,9993 / 1,0 ; 0,852. 0,5 → 0,9987 / 0,9986 / 1,0 ; 0,859. **0,6 → 0,998 / 0,9986 / 0,9996 ; 0,881.** 0,7 → 0,9971 / 0,9972 / 0,9996 ; 0,882. 0,8 → 0,9956 / 0,9933 / 0,9952 ; 0,883.
  - Filtre seul (0,3) : 0,9979 / 0,9993 / 0,9994 ; 0,868. Filtre + 0,6 : 0,9957 / 0,9968 / 0,9986 ; 0,884.
  - Nombres recouverts : 4 ou 5 sur 21 722 partout.
  - Au-delà de 0,6, la précision plafonne vers 0,88 : les faux positifs restants ne viennent plus de GLiNER (« P.V. » par le motif d'initiales de D4, en-têtes tout en majuscules « PROCÈS-VERBAL D'AUDITION », « Réf », « Référence » par spaCy). « Nous », « Je », « Date » disparaissent dès 0,6.
- **Décisions :** aucune appliquée ; `configs/ingest.yaml` inchangé.
- **Écarts avec SPEC.md :** aucun.
- **Questions pour Raphael :** passer le seuil de GLiNER de 0,3 à 0,6 (recommandé : précision +6 points, rappel PER −0,001) ? Le filtre de propagation coûte plus de rappel qu'il ne retire de faux positifs : je ne le recommande pas.
- **Suite prévue :** selon la réponse, seuil 0,6 dans `configs/ingest.yaml` ; puis faux positifs de spaCy et D4 sur les en-têtes, et étape suivante de la phase 2 (relations et slots, SPEC.md §6).

## 2026-10-22 — Phase 2 — Seuil de GLiNER à 0,6
- **Travail fait :** `detection.gliner.seuil` passé de 0,3 à 0,6 dans `configs/ingest.yaml` (accord de Raphael).
- **Mesures :** celles de l'entrée précédente (validation) : rappel PER 0,998, ORG 0,9986, LIEU 0,9996, REF 1,0 ; précision des zones 0,881. `make test` : 147 tests passés.
- **Décisions :** seuil 0,6 ; pas de filtre de propagation.
- **Écarts avec SPEC.md :** §6 donne « seuil bas (0,3) » pour D1 ; c'est une valeur de départ, changée sur mesure (§15). SPEC.md non modifié.
- **Suite prévue :** faux positifs restants (spaCy et D4 sur les en-têtes, « P.V. ») ; puis relations et slots (SPEC.md §6).

## 2026-10-22 — Phase 2 — Anonymiseur (§6) et T2
- **Travail fait :** tâche donnée par Raphael. Tests écrits avant le code (§3) : `tests/unit/test_anonymiseur.py` (35 : analyse des noms, chaque relation, alias, titres, attributs des nombres, table, exemple sans nom, tables NN/PP, commande) et `tests/unit/test_t2_anonymiseur.py` (T2 sur 3 dossiers et un témoin). Code : `ccm/anonymize/names.py` (analyse PER : prénoms, nom de famille, initiales), `relations.py` (relations 2 à 14), `units.py` (grandeur, rang, signe), `table.py` (table de la conversation), `exemple.py` (`anonymiser` : stock → exemple JSON de §4 ; `lire_message` : détecteurs + noms connus + nombres), `encode.py` (tables NN et PP de §8, numéros locaux par première apparition). `ccm/eval/equivariance.py` : stock de référence (faits du dossier comme mentions et nombres, sans détecteurs), bijection, renommage, forme canonique. Commande `ccm anonymize QUESTION --stock BASE [--prop ID …] [--conv ID] [--graine N] [--sortie F]`. Config : `noms.genres`, `noms.alias`, bloc `anonymiseur` (K = 256, grandeur [−3, 12], rang ≤ 63, `ocr_bas` 0,85). Dépendance : `rapidfuzz` 3.14.6 (MIT), prévue par §3.
- **Mesures :**
  - **T2 exact** : 3 dossiers d'entraînement (graines 0 à 2), toutes leurs questions (environ 40 chacun), contexte des 150 premières propositions (limite de §8 ; le dossier 0 en a 153), une contrainte MEME. Exemples égaux après mise en ordre, tables NN et PP égales, avec deux graines de table différentes. Le dossier 0 contient un alias (« Hélène Bornier, dit Jojo ») et un conflit établi (HEURE). Durée : 6 s.
  - Témoin : si les mentions PER restent en clair, la comparaison de T2 échoue (test `test_t2_detecte_une_fuite`).
  - Un exemple de 150 propositions : 14 ms. Relations (dossier 1, mentions de référence, 54 noms, 89 valeurs) : MEME_FAMILLE 24, INCLUS_DANS 13, INITIALES_DE 10, SIGLE_DE 5, INCOMPATIBLE 4, PROCHE 1 ; SUIVANTE 113.
  - `ccm anonymize` sur un stock ingéré avec les vrais détecteurs (`syn-1000000` de validation, 73 propositions gardées) : 32 s, dont le chargement de GLiNER et spaCy. Question « … de la société delcoron le 13 mars 2025 ? » → « … de la société delcoron le ⟦0⟧ ? » : **« delcoron » reste en clair** (voir écarts).
  - `make test` : 186 tests passés. Un premier passage a échoué sur `test_pieces.py::test_relire_montant` (délai de 200 ms d'Hypothesis dépassé au premier appel, 1 s) ; passé seul puis sur toute la suite. Test de la phase 1, non modifié.
- **Décisions :**
  - **Indice `nom` unique pour tous les types.** `relations_noms` (§4) ne porte pas le type, et les indices sont tirés par type. Le réservoir du type de rang r (PER, ORG, LIEU, REF, AUTRE, ordre de §8) occupe les indices r·K à r·K + K − 1 : ce sont les 1 280 vecteurs de slots de §8. L'exemple de §4 (PER 3 et 5) reste valide.
  - Tirage : une permutation de 0 … K − 1 par réservoir, graine « graine:type » ; noms et valeurs dans l'ordre de première apparition (historique, question, propositions). Plus de K noms d'un type, ou plus de K valeurs distinctes : erreur. Les valeurs ont leur propre réservoir de K indices ; `valeur_id` égal pour une même valeur décimale (« 1250.00 » = « 1250 ») et une même unité.
  - MEME_CHAINE : diagonale de NN, pas dans `relations_noms` (qui porte les relations 2 à 14, comme l'en-tête de A0). MEME_PROPOSITION et MEME_PIECE : calculées par `encode` (diagonale et champ `piece`), pas dans `relations_props`. CONFLIT et DOUBLON_DE rendus une fois (symétriques) ; MEME_SECTION par une même arête SECTION_DE.
  - Un nom (norme, type) peut avoir plusieurs surfaces ; une relation vaut si elle vaut pour un couple de surfaces. Relation symétrique : une fois, plus petit indice d'abord.
  - INCOMPATIBLE : lu comme « même nom de famille, et (prénoms incompatibles ou titres de genre différent) ». Sans la condition de famille, tout « M. X » serait incompatible avec toute « Mme Y ». Titre = mot écrit juste devant la mention (`noms.genres` : m, monsieur → M ; mme, mlle, madame… → F). Prénoms comparés mot à mot : égaux, initiale (« j » / « jean ») ou préfixe de mots (« jean » / « jean pierre ») ; « jean » / « jeanne » sont incompatibles.
  - INITIALES_DE : a écrit en initiales (tout type) ; b PER avec prénoms et nom de famille ; initiales des prénoms, ou des prénoms et des mots du nom de famille sans les particules. SIGLE_DE : a = 2 à 8 majuscules, points retirés ; mots pleins de b = mots hors mots vides et particules écrits en minuscules, au moins deux. PROCHE : longueur = la plus courte des deux normes ; Damerau-Levenshtein sans restriction (rapidfuzz). PROCHE, SIGLE_DE, INCLUS_DANS : tous types.
  - ALIAS_DECLARE : deux mentions voisines dont le texte entre les deux est exactement un motif de `noms.alias` (les six motifs de §6, avec leurs formes féminines « dite », « surnommée », « née », et « ci-après « … » »).
  - Nom PER d'un mot seul en minuscules : rôle inconnu, pas de nom de famille (`nom_famille` rendait sa norme). Les tests des conflits passent ; la mesure des conflits n'est pas refaite.
  - Nombres : grandeur = exposant décimal exact (`Decimal.adjusted`), rien pour zéro ; rang dense par unité, les dates en ordre ISO.
  - `ccm anonymize` : sans recherche (§7 pas faite), le contexte est `--prop` ou toutes les propositions gardées (plus de 150 : erreur du schéma). Un appel = une conversation : la table n'est pas gardée d'un appel à l'autre. MEME_HYPOTHESE vient d'un paramètre (`hypotheses`), vide tant que le modèle n'existe pas. `encode` ne fait que NN et PP ; `input_ids` et les autres tables attendent le tokenizer.
  - T2 : bijection = permutation sans point fixe des 26 lettres, mot par mot (mots séparés par blancs et tirets), accents retirés, casse gardée ; titres, particules et mots vides en minuscules restent fixes ; permutation refusée si un mot renommé devient un mot fixe (graines 0, 1, … jusqu'à la première valide). Elle garde normes, distances, initiales, inclusions et motifs d'alias. Le stock de référence calcule aussi les conflits établis.
- **Écarts avec SPEC.md :** aucun sur les règles. Points ouverts :
  - **Fuite par un nom partiel dans un message** : « delcoron » n'est pas trouvé, car la recherche sans casse de §6 cherche les noms connus entiers (« sarl delcoron »). Ce n'est pas couvert par T2 (mentions de référence). C'est un défaut de détection, que T3 mesurera.
  - `test_relire_montant` peut dépasser son délai sur une machine chargée.
- **Questions pour Raphael :**
  1. Messages de l'utilisateur : chercher aussi, sans casse, chaque mot d'un nom connu (nom de famille PER, mot distinctif d'un ORG) ? Plus de rappel, mais des faux positifs (« caron », « vy »). À mesurer avant de décider.
  2. Lecture d'INCOMPATIBLE (famille commune exigée aussi pour les titres) : d'accord ?
  3. Indices `nom` par blocs de type (0 à 1 279) : d'accord ?
- **Suite prévue :** recherche (SPEC.md §7) : départs par noms et par texte, extension, classement, second tour, contraintes, budget ; commande `ccm search` ; mesure du rappel des justificatives dans le budget.

## 2026-10-22 — Phase 2 — Noms partiels dans les messages : mesure
- **Travail fait :** réponses de Raphael : lecture d'INCOMPATIBLE validée ; indices `nom` par blocs de type validés ; mesurer la recherche des mots des noms connus. `detecter_message` découpé en `connus` et `chercher_connus` (comportement inchangé). `ccm/eval/messages.py` : `uv run python -m ccm.eval.messages runs/corpus/niveau0/validation runs/messages/validation` (validation réingérée avec GLiNER à 0,6, un processus, environ 10 min).
- **Mesures (validation, 200 dossiers, 8 314 messages de l'utilisateur ; les messages du corpus ne nomment que des PER et des ORG) :**
  - Variantes de la recherche sans casse : V0 = normes connues entières (règle actuelle) ; V1 = V0 + noms de famille des mentions PER ; V2 = V0 + chaque mot d'au moins 3 lettres des noms connus, sauf titres, particules, mots vides et mots courants des lexiques de D4 (lexique lu sur le mot écrit, avec ses accents).
  - Conditions : messages tels qu'écrits par le générateur ; mêmes messages, chaque nom réécrit en minuscules sans accents (« dupont »). Les questions du corpus n'écrivent jamais un nom en minuscules : sans la seconde condition, la mesure ne voit pas le cas.
  - Tels qu'écrits : PER 0,9987 et ORG 1,0 pour les trois variantes ; 12 messages avec fuite (surnoms à article : « le Prof », « le Chat ») ; faux positifs 640 (V0, V2), 649 (V1).
  - En minuscules : V0 PER **0,9711**, ORG 0,9969, **246** messages avec fuite, 641 faux positifs ; V1 0,9767, 197, 650 ; V2 PER **0,9858**, ORG 0,9969, **124** messages avec fuite, **641** faux positifs.
  - Premier essai de V2 : 298 faux positifs « société », parce que le lexique était lu sur la norme sans accents (« societe ») ; corrigé, puis remesuré (chiffres ci-dessus).
  - Manques restants (V2, minuscules) : surnoms à article (« le marseillais », « le belge »), noms qui sont des mots courants (« fontaine », « robert », « morel », « lucas », « clement »), initiales (« l.m. »).
  - Faux positifs de toutes les variantes, déjà dans V0 : « montant » 537 sur 641. À l'ingestion, « Montant » (en-têtes de tableaux) est lu comme un nom (199 mentions PER, 61 AUTRE) ; la recherche des normes connues le masque ensuite dans « Quel est le montant… ». Aussi « Additionnés » 46, « le » 32 (norme « le » connue, AUTRE), « même » 18.
  - `make test` : 186 tests passés. `test_relire_montant` a de nouveau dépassé son délai de 200 ms au premier passage (1 s ; 0 ms en isolé : charge de la machine) ; passé au second. Non modifié.
- **Décisions :** aucune règle changée ; `ner/propagate.py` garde V0.
- **Écarts avec SPEC.md :** aucun.
- **Questions pour Raphael :**
  1. Adopter V2 dans `detecter_message` ? Recommandé : en minuscules, deux fois moins de messages avec fuite (246 → 124), sans faux positif de plus ; neutre sur les messages bien écrits.
  2. « Montant » lu comme un nom à l'ingestion, puis masqué dans les questions : le modèle perd le mot « montant » de la question. Corriger les faux positifs d'en-têtes à l'ingestion (déjà dans la suite prévue), ou ne pas chercher dans les messages une norme connue qui est un mot courant du lexique ?
  3. `test_relire_montant` (phase 1) échoue parfois sur son délai, jamais sur le résultat. Lever le délai de ce test (`deadline=None`) ? Le résultat attendu ne change pas.
- **Suite prévue :** selon les réponses, V2 dans `detecter_message` ; puis la recherche (SPEC.md §7) et `ccm search`.

## 2026-10-22 — Phase 2 — V2 dans la chaîne des messages
- **Travail fait :** réponses de Raphael : V2 adopté ; délai de `test_relire_montant` levé ; question « montant » à réexpliquer. `ner/propagate.py` : `mots_connus` (code de V2 déplacé depuis `eval/messages.py`), utilisé par `detecter_message`. Test `test_message_utilisateur_mot_d_un_nom` (« eloi », « dupont », « gerard » trouvés ; « société » non). `test_relire_montant` : `@settings(deadline=None)`, résultat attendu inchangé.
- **Mesures :** `make test` : 187 tests passés. Pas de remesure : le code de V2 est celui mesuré (rappel PER en minuscules 0,9858, 124 messages avec fuite).
- **Décisions :** aucune règle changée hors V2, validé.
- **Constat « montant » :** spaCy lit l'en-tête de tableau « Date | Libellé | Montant » comme un nom PER (193 mentions spaCy seul, 67 propagation et spaCy, sur les 200 dossiers de validation). Aucune personne du corpus ne s'appelle Montant.
- **Écarts avec SPEC.md :** aucun.
- **Suite prévue :** selon la réponse de Raphael sur « montant » ; puis la recherche (SPEC.md §7) et `ccm search`.

## 2026-10-22 — Phase 2 — En-têtes de tableaux hors des noms
- **Travail fait :** réponse de Raphael : option (a), corriger à l'ingestion. `ner/union.py` : `en_tete_tableau` ; dans `detecter`, une ligne d'en-tête de tableau (au moins deux cellules « | », aucun chiffre, chaque mot courant dans les lexiques) ne garde que ses références. Tests `test_en_tete_tableau`, `test_detecter_en_tete_tableau_sans_nom`.
- **Mesures (validation réingérée, `runs/messages/validation-entetes`) :** rappels inchangés (en minuscules, V2 : PER 0,9858, ORG 0,9969, 124 messages avec fuite). Faux positifs des messages : 641 → **104** (V2, minuscules), 640 → 103 (tels qu'écrits) ; « montant » n'en fait plus partie. Restent : « Additionnés » 46, « le » 32, « même » 18, « petit » 5. Dans le corpus, les lignes de tableau sans chiffre sont les seuls en-têtes (4 formes) et ne contiennent aucun nom. `make test` : 189 tests passés.
- **Décisions :** règle limitée aux lignes sans chiffre faites de mots courants, pour ne jamais retirer un nom d'une ligne de données.
- **Écarts avec SPEC.md :** aucun.
- **Suite prévue :** recherche (SPEC.md §7) : départs par noms et par texte, extension, classement, second tour, contraintes, budget ; `ccm search` ; mesure du rappel des justificatives dans le budget.

## 2026-10-25 — Phase 2 — Recherche (§7) et `ccm search`
- **Travail fait :** tâche donnée par Raphael (l'anonymiseur §6 était déjà fait le 2026-10-22). Tests écrits avant le code : `tests/unit/test_recherche.py` (18 : départs par noms et noms reliés, départs par texte, extension, dépendances et conflits, budgets, groupe trop grand, ordre du contexte, classement, second tour, question de suite, citées avant, contraintes MEME et IGNORER_SOURCE, doublons, trace et déterminisme, commande) et `test_t7_recherche_hors_ligne` (T7). Code : `search/bm25.py` (`Index`, `charger_index`), `search/expand.py` (`Graphe` : index inversé norme → propositions, noms reliés, extension, fermeture ; `jetons`), `search/retrieve.py` (`chercher`, `ecrire_trace`), `anonymize/relations.py` (`relations_entre`). Commande `ccm search QUESTION --stock BASE [--precedente M …] [--citee ID …] [--conv ID] [--jetons N] [--sans-trace] [--sortie F]`. `configs/search.yaml` : départs, classement, second tour, budget, jetons (valeurs de départ de §7). Mesure : `ccm/eval/recherche.py`.
- **Mesures (validation, 200 dossiers réingérés, 7 142 questions avec étapes, 11 142 justificatives ; questions lues avec les vrais détecteurs) :**
  - **Rappel des justificatives dans le budget (3 500 jetons, 150 propositions) : 0,998** (seuil 0,95). Par type : CALCUL 1,0 ; CONFLIT 0,9993 ; DIALOGUE 1,0 ; FAIT_SIMPLE 1,0 ; IDENTITE 1,0 ; PLUSIEURS_ETAPES 0,9952. Rappel « étape » (une ligne équivalente suffit) : 0,9983. 22 justificatives manquées, presque toutes des chaînes de 3 à 5 personnes (« la personne qui a rencontré la personne entendue en même temps que X »). 0 ligne non retrouvée à l'ingestion. 316 questions de conflit sans nom (départ par texte seul).
  - Contexte moyen : 76 propositions, 2 161 jetons, **65 % du stock** du dossier : les dossiers du niveau 0 sont petits (73 à 123 propositions gardées dans l'essai), le budget prend une bonne partie du dossier. Le rappel mesure donc peu le classement.
  - Contrôle du classement, budget serré de 1 000 jetons (27 % du stock) : rappel 0,9425 ; FAIT_SIMPLE 1,0, IDENTITE 0,984, CONFLIT 0,994, CALCUL 0,99, DIALOGUE 0,997, **PLUSIEURS_ETAPES 0,864**.
  - 83 ms par question (`Graphe` reconstruit à chaque appel). Premier lancement (3 processus) arrêté par Claude Code pour manque de mémoire ; relancé avec 1 processus.
  - `make test` : 208 tests passés (avant la mesure).
- **Décisions :**
  - Index inversé : dictionnaire norme → propositions gardées, construit depuis la table `mention` à chaque recherche ; pas de nouvel index SQLite.
  - Noms reliés (étape 1) : relations MEME_FAMILLE, INITIALES_DE, INCLUS_DANS, PROCHE, SIGLE_DE dans un sens ou dans l'autre, avec tous les noms du stock ; la norme seule fait la clé (pas le type). Propositions de norme égale d'abord, puis celles des noms reliés, chacune classée par BM25, 40 au plus par nom.
  - Extension (étape 2) : SUIVANTE et CONFLIT dans les deux sens ; DEPEND_DE en fermeture dans les deux sens. Fermeture de l'étape 6 : dépendances (sens src → dst) et conflits, jusqu'au point fixe. Un groupe qui dépasse le budget (propositions, jetons, ou K = 256 noms d'un type) saute ; les suivants sont essayés.
  - BM25 normalisé par le meilleur score de la question sur l'index. « Noms couverts » : noms de la question (et des contraintes MEME) dont la proposition contient la norme ou une norme reliée. Bonus de départ pour les départs par nom ou par texte, tous tours.
  - Second tour : noms nouveaux pris dans l'ordre du classement puis de l'écrit, tous types (AUTRE compris) ; ils ne comptent pas dans les noms couverts.
  - Question de suite : noms du message précédent le plus récent qui en a. Citées avant : entrent d'abord, hors budget si besoin. IGNORER_SOURCE retire aussi les citées de la pièce (et des sous-pièces « id.n »).
  - Jetons en attendant le tokenizer : 4 + ⌈1,6 × mots⌉ par proposition (`configs/search.yaml`).
  - Trace : `reponse_id` = uuid4, `chemin_recherche` = raisons de chaque proposition dans l'ordre du contexte (noms de départ, texte, sauts, tour, citée avant, score), `revision_base`. `ccm search` l'écrit sauf `--sans-trace`.
  - Mesure : justificative trouvée si sa proposition, ou la gardée de son groupe de doublons, est rendue. Dialogue : les lignes citées par la réponse précédente de référence entrent comme `citees`.
- **Écarts avec SPEC.md :** aucun sur les règles. Le seuil de rappel de la phase 2 passe sur la validation ; la mesure finale sur le test reste à faire une seule fois en fin de phase.
- **Questions pour Raphael :**
  1. Le niveau 0 est trop petit pour juger le classement (65 % du stock dans le contexte). Garder la mesure à 1 000 jetons comme contrôle dans le rapport de phase ?
  2. Plusieurs étapes à budget serré (0,864) : les chaînes de 3 à 5 personnes demandent plus de 2 tours. À regarder plus tard, ou ne rien changer (seuil atteint) ?
- **Suite prévue :** rapport de phase 2 (`reports/phase-2.md`) : tableau seuils contre mesures (noms PER, rappel de la recherche, T2, conflits), mesures finales sur le test une seule fois, relecture avec Raphael avant `phase-2-ok`.

## 2026-10-25 — Phase 3 — Grammaire (§10, §10 bis) et T4
- **Travail fait :** **accord de Raphael ce soir pour commencer la phase 3 avant la clôture de la phase 2** (rapport, mesure sur le test et `phase-2-ok` restent à faire). Branche `phase-3` créée depuis `phase-2` (et non `main`) : la grammaire lit les exemples de l'anonymiseur, pas encore fusionnés. Tests écrits avant le code : `tests/unit/test_grammaire.py` (20 : lexique, algèbre des unités, chaque règle du masque, budget de pas, synthèse, décodages au hasard) et `tests/unit/test_t4_automate.py` (T4 et T10 : suites de référence de 4 dossiers générés, chaque pas dans son masque, en mode citation et en mode synthèse ; 2 × 1 000 décodages au hasard). Code : `schema.py` (`LEXIQUE_SYNTHESE` : 25 + 5 = 30 jetons), `grammar/lexicon.py`, `grammar/units.py` (algèbre des unités, décimal exact), `grammar/automaton.py` (`Contexte`, `Automate`, `masques`, `accepter`, `decoder_au_hasard`), `anonymize/table.py` (`valeurs` : valeur_id → valeur, pour le masque, hors du modèle), `data/worldgen/cibles.py` (suites de référence de §10 depuis la vérité terrain), `eval/grammaire.py` (mesure). `configs/grammar.yaml` (`GrammarConfig`).
- **Mesures :**
  - `uv run python -m ccm.eval.grammaire 100000 runs/grammaire/bilan.json` (126 dossiers d'entraînement générés, mentions de référence) : **10 054 / 10 054 suites de référence acceptées** (5 027 questions, en mode citation et en mode synthèse) ; **100 540 / 100 540 décodages au hasard valides**, aucune impasse, fin par FIN, relus par l'automate ; longueur maximale 96 (citation) et 512 (synthèse), les limites. 457 s.
  - Premier passage : 4 suites refusées (2 questions ASK_SAME du dossier 50, trois personnes possibles, écrites `ASK_SAME M M M`). Corrigé dans `cibles.py` (grammaire inchangée), dossier 50 ajouté à T4.
  - Longueur des suites de référence en mode citation : 14 pas au plus sur 6 dossiers.
  - `make test` : 235 tests passés.
- **Décisions :**
  - Pas : `P:k`, `M:t.j`, `N:t.j` (format de `cible`, §4), mot de synthèse `W:mot`. Un mot = `\w+['’]?` ou un signe de ponctuation (« l'heure. » → « l' », « heure », « . »). Les 40 mots d'une phrase ne comptent pas la ponctuation.
  - Aucune impasse et limite de pas : un pas n'est permis que si la réponse peut encore finir dans la limite (longueur minimale de chaque segment, de la fermeture d'un bloc, de la synthèse).
  - CALCUL : opérandes distincts (« deux nombres cités », §10) ; une pile n'accepte un opérande ou un opérateur que si elle reste réductible par des opérateurs seuls (unité, précision, valeur non nulle connue pour ÷, durée entière pour DATE ± durée) ; 12 pas entre CALCUL et FIN_CALCUL. Ouverture : deux nombres cités qui se combinent.
  - Algèbre : un nombre sans unité est un rapport sans unité ; % vaut sa valeur / 100 ; DATE − DATE donne l'unité « jour », et DATE ± durée n'accepte que « jour ». Une date ne se calcule qu'à la précision JOUR ; MIN et MAX de dates de même précision. **DATE + DATE interdit** (la ligne « +, −, MIN, MAX : même unité » le permettrait à la lettre).
  - CONFLIT : P du bloc sans condition « non citée » ; ils deviennent cités, comme la preuve d'un SAME. DECLARATION : contrainte MEME_UTILISATEUR ou DIFFERENT_UTILISATEUR entre les deux noms ; P suivants : toute proposition hors du bloc, sans maximum. SAME, ASK_SAME : mentions de tous les textes (question, historique, propositions). NOTE_SAME, NOTE_DIFF : mentions de la question.
  - Synthèse : une seule par réponse ; une source sans marque n'est permise que si une source marquée peut suivre ; dépendances DEPEND_DE en fermeture transitive. Majuscule : forme `Mot` d'un mot de V, au premier élément après DEBUT. La synthèse vient avant FIN.
  - Suites de référence : NOTE_* d'abord ; étape PREUVE portée par le P du SAME ; bloc CONFLIT seulement si la première ligne a une arête CONFLIT vers les autres (sinon des citations) ; DECLARATION_FAUSSE : NOTE_SAME puis la citation (le corpus ne donne pas de preuve contraire) ; ASK_SAME à plus de deux personnes : un ASK_SAME par paire avec la première, liés par ET.
  - Liste V absente (phase 5) : les tests prennent comme V les mots des synthèses de référence du dossier ; pas d'arbre de préfixes BPE (pas de tokenizer).
- **Écarts avec SPEC.md :**
  - **Limite de pas de la synthèse.** S ≤ 96 (§8) ne tient pas avec la synthèse (8 phrases de 40 mots) : 12 suites de référence sur 2 008 de la validation dépasseraient 96 pas (toutes CALCUL), en mots entiers. T4 garde 96 pour le mode citation ; la synthèse a sa limite, `pas_max_synthese` = 512, provisoire.
- **Questions pour Raphael :**
  1. Limite de pas d'une réponse avec synthèse : 512 ? (En jetons BPE, il en faudra plus que des mots.)
  2. DATE + DATE interdit : d'accord ?
  3. ASK_SAME à trois personnes possibles : un ASK_SAME par paire avec la première, d'accord ? Ou ajouter une forme à la grammaire ?
  4. Opérandes distincts dans un CALCUL : d'accord ?
- **Suite prévue :** retour à la phase 2 : rapport `reports/phase-2.md`, mesure finale sur le test, relecture avant `phase-2-ok`. Puis, en phase 3 : vérificateur et rendu (§11), modèle oracle, `ccm answer --oracle`.

## 2026-10-25 — Phase 2 — Mesure finale sur le test, rapport
- **Travail fait :** retour sur `phase-2` (Raphael : clore la phase 2 avant la suite ; la grammaire attend sur `phase-3`). Mesure finale, une seule fois, sur les 200 dossiers de test : `ccm.eval.noms`, `ccm.eval.conflits`, `ccm.eval.recherche` (un processus chacun, `runs/final/`). Conflits remesurés sur la validation avec le code actuel. `reports/phase-2.md`.
- **Mesures (test) :** rappel PER 0,9973 ; rappel des justificatives dans le budget 0,9966 ; conflits heure et montant : **précision 0,807** (46 VP, 11 FP), rappel 0,687. Validation, code actuel : précision 0,970, rappel 0,80.
- **Décisions :** aucun réglage sur le test ; faux positifs du test non regardés.
- **Écarts avec SPEC.md :** **seuil de précision des conflits (0,9) non atteint sur le test.** Pas d'étiquette `phase-2-ok`, pas de fusion.
- **Questions pour Raphael :** voir `reports/phase-2.md` (que faire de la précision des conflits : second jeu de validation à gabarits neufs, accepter l'écart, ou changer le seuil).
- **Suite prévue :** selon la décision de Raphael sur les conflits.

## 2026-10-25 — Phase 2 — Fin de phase
- **Travail fait :** décision de Raphael sur la précision des conflits du test (0,807 < 0,9) : option (b), écart accepté et écrit dans `reports/phase-2.md`, phase close. Étiquette `phase-2-ok`, fusion de `phase-2` dans `main`.
- **Mesures :** `make test` sur `phase-2` avant l'étiquette (ci-dessous).
- **Décisions :** la règle des conflits reste celle réglée sur la validation.
- **Écarts avec SPEC.md :** précision des conflits établis sur le test 0,807 (seuil 0,9), accepté par Raphael.
- **Suite prévue :** phase 3 sur `phase-3` (grammaire faite, à rebaser sur `main`) : questions de la grammaire en attente (limite de pas de la synthèse, DATE + DATE, ASK_SAME à trois personnes, opérandes distincts), puis vérificateur et rendu (§11), modèle oracle, `ccm answer --oracle`.

## 2026-10-25 — Phase 3 — Réponses sur la grammaire
- **Travail fait :** réponses de Raphael aux questions de la grammaire : (1) `pas_max_synthese` = 512 validé ; (2) DATE + DATE interdit, validé ; (3) ASK_SAME à plus de deux personnes : une paire par personne, validé ; (4) **opérandes distincts refusés** : un CALCUL peut reprendre un même nombre. `automaton.py` : réemploi permis ; l'ouverture d'un CALCUL demande toujours deux nombres cités qui se combinent (§10, « Aucune impasse »). Test `test_calcul` : réemploi permis.
- **Mesures :** `make test` : 235 tests passés. `ccm.eval.grammaire 100000` : 10 054 / 10 054 suites de référence acceptées, 100 540 / 100 540 décodages valides, aucune impasse (507 s).
- **Décisions :** voir ci-dessus.
- **Écarts avec SPEC.md :** aucun de plus.
- **Suite prévue :** vérificateur et rendu (§11), modèle oracle, `ccm answer --oracle`.

## 2026-10-26 — Phase 3 — Suites de référence du corpus et T10
- **Travail fait :** tâche donnée par Raphael : suites de référence (§10, « Ordre des suites de référence ») pour toutes les questions de la phase 1, et T10. `ccm/data/worldgen/suites.py` : lit le corpus écrit (`verite.json`, `questions.json`), construit stock de référence, exemple et cible de chaque question, en mode citation et en mode synthèse (si la question en a une), contrôle chaque pas dans son masque (`premier_refus`), écrit `cibles.json` dans chaque dossier (pas et jetons, aucune chaîne de nom ; dans `runs/`, hors de git) et le bilan `runs/corpus/niveau0/cibles.json`. `uv run python -m ccm.data.worldgen.suites runs/corpus/niveau0 8`. Test `tests/unit/test_t10_masque_reference.py` (T10) : 10 dossiers générés, chaque pas de chaque suite dans son masque ; couverture des 7 types, des 5 sous-types de dialogue, des deux blocs de conflit, d'ABSTENTION, SAME, NOTE_*, ASK_SAME, DONC CALCUL, SYNTHESE ; un pas hors du masque est refusé.
- **Mesures :**
  - Entraînement (2 000 dossiers) : **79 953 / 79 953** suites citation, **71 158 / 71 158** suites synthèse acceptées. Validation (200) : 8 000 / 8 000 et 7 141 / 7 141. Test (200) : 7 982 / 7 982 et 7 123 / 7 123. **0 refus**, 0 erreur de construction. 544 s, 8 processus.
  - Longueur maximale : 14 pas (citation, limite 96) ; 107 pas (synthèse, limite 512).
  - Conflits : entraînement 3 610 blocs CONFLIT (établis), 3 364 CONFLIT SANS_PREUVE ; validation 466 / 233 ; test 361 / 371.
  - `make test` : 247 tests passés.
- **Décisions :**
  - **Conflit supposé** : une question CONFLIT (versions contradictoires de la vérité terrain) sans arête CONFLIT dans le contexte s'écrit `CONFLIT SANS_PREUVE P P FIN_CONFLIT` (§10, règle 4 ; §12 : moitié CONFLIT, moitié SANS_PREUVE). Avant, `cibles.py` l'écrivait en citations : aucune suite de référence n'avait de CONFLIT SANS_PREUVE. Corrigé dans `cibles.py` ; grammaire et automate inchangés.
  - Vocabulaire V provisoire de la synthèse : mots des synthèses de référence du dossier (comme T4), en attendant la liste V de la phase 5.
  - Les suites du test sont construites (pour l'évaluation) ; aucun réglage fait d'après elles : toutes acceptées au premier passage.
- **Écarts avec SPEC.md :** aucun de plus. DIALOGUE/DECLARATION_FAUSSE reste NOTE_SAME puis la citation (décision du 2026-10-25) : sans contrainte de l'utilisateur dans l'exemple, CONFLIT DECLARATION est masqué.
- **Suite prévue :** vérificateur et rendu (§11), modèle oracle, `ccm answer --oracle`.

## 2026-10-27 — Phase 3 — Vérificateur (§11, étapes 1 à 9)
- **Travail fait :** tâche donnée par Raphael : vérificateur avec la règle d'ancrage et le calcul en décimal exact. `ccm/verify/verifier.py` (étapes 1 à 9, `verifier(con, Entree, suite, …)` → `Reponse` : blocs, citations, erreur, ligne de trace), `ccm/verify/render.py` (gabarits fixes de §11, écriture des nombres ; chaque fragment affiché porte son origine), `ccm/verify/trace.py`, `configs/verify.yaml`. `anonymize/exemple.py` : `zones_message` et `zones_propositions`, appelées par l'anonymiseur et par le vérificateur (une marque ⟦j⟧ = la zone j ; aucune copie). Tests : `tests/unit/test_verificateur.py` (petit stock écrit à la main pour chaque étape ; suites de référence des dossiers 0, 10, 50, résultats des calculs contre la vérité terrain) ; `tests/property/test_t5_rendu_ferme.py` (T5 : décodages au hasard sous masque, mode citation et synthèse, dossiers 0, 1, 2, 10, 50 ; chaque fragment dans son ensemble ; un fragment étranger est refusé).
- **Mesures :** `make test` : 284 tests passés (247 avant), 171 s. T5 : 0 fragment hors des ensembles, 0 erreur de vérification sur les décodages au hasard et sur les suites de référence.
- **Décisions :**
  - Décimal exact : `fractions.Fraction` (aucune perte, même pour 1/3). Un résultat sans écriture décimale finie s'affiche arrondi à `decimales` = 2, précédé de « ≈ ». Dates JJ/MM/AAAA ; heure du jour « 21 h 59 » ; pourcentage × 100 suivi de « % » ; durée « N jours ».
  - Ancrage : « même nom » = même indice de nom de la table (même norme, même type). Question sans nom : les noms du message le plus récent de l'historique qui en a (comme la recherche, §7). Relations 2 à 11 prises à la lettre (MEME_FAMILLE, INITIALES_DE, PROCHE, INCOMPATIBLE, SIGLE_DE, INCLUS_DANS, ALIAS_DECLARE). Propositions citées : CITE, preuve d'un SAME, propositions des blocs CONFLIT, SANS_PREUVE et DECLARATION.
  - Conflits (étape 4) : contrôlés pour toutes les propositions citées, y compris celles d'un bloc CONFLIT SANS_PREUVE ; le bloc supposé lui-même n'ajoute rien. « Sa date » : les dates lues dans la phrase (la table `piece` n'a pas de date).
  - Passages non cités : `seuil_selection` = 0,5, valeur de départ, à régler sur la validation (rappel 0,95) quand le modèle donnera des probabilités (phase 4).
  - Étape 8 : la relance est une fonction `relancer` fournie par l'appelant (`ccm answer`), appelée une fois ; les notes de la première réponse restent en tête.
  - Étape 9 : si la recherche a déjà écrit la ligne de trace (`reponse_id`), le vérificateur la complète (`actions`, `modele`) ; sinon il en écrit une.
  - SAME avec preuve : « Source [n] : » au lieu de « Source : », pour relier les opérandes d'un calcul à cette citation.
- **Écarts avec SPEC.md :**
  - T5 : la pièce, la page, le rang et le numéro de citation sont une cinquième origine (« ref », lue dans le stock), hors des quatre ensembles de §11. Les gabarits de §11 les demandent. **Validé par Raphael le 2026-10-27** ; SPEC.md §11 (test de propriété) mis à jour.
  - Doublons (§5, étape 7), demande de Raphael : sous chaque passage affiché, « Aussi dans : pièce X, page Y ; … », une fois par réponse ; au plus `doublons_max` = 3 endroits (valeur de départ, `configs/verify.yaml`), puis « et N autres endroits », pour ne pas manger le budget d'affichage. `make test` : 285 tests passés.
- **Suite prévue :** modèle oracle, `ccm answer --oracle` de bout en bout (recherche, anonymiseur, oracle, vérificateur, relance après NOTE_*).

## 2026-10-28 — Phase 3 — T9, T11 et 100 000 décodages sous masque
- **Travail fait :** tâche donnée par Raphael : rendu et gabarits (§11), T5, T9, T11, test des 100 000 décodages aléatoires sous masque. Rendu, gabarits et T5 faits le 2026-10-27 ; chaque ligne du tableau de §11 a son gabarit dans `verify/render.py` (contrôlé). `tests/unit/test_t9_determinisme.py` (T9) : deux processus neufs, `PYTHONHASHSEED` différents, écrivent le dossier de graine 7 (PDF, `verite.json`, `questions.json`, `cibles.json`) puis décodent chaque question (glouton et au hasard, citation et synthèse) et vérifient ; fichiers égaux octet pour octet, réponses égales. `tests/property/test_t11_synthese.py` (T11) : 100 000 décodages au hasard en mode synthèse ; chacun valide (FIN, `pas_max_synthese`, `accepter`), vérifié sans erreur, rendu contrôlé comme T5 ; chaque phrase : aucun chiffre, aucun mot hors de V, chaque nom et nombre affiché pris dans les sources de la phrase et leur fermeture DEPEND_DE lue dans le stock, chaque pointeur vers l'une d'elles.
- **Mesures :** T11 : **100 925 / 100 925 décodages valides**, 47 219 avec synthèse, 94 257 phrases contrôlées, 0 erreur (104 dossiers). T5 + T9 + T11 ensemble : 14 passés, 437 s. `make test` : **287 tests passés**, 552 s.
- **Décisions :**
  - T9, décodage glouton : le modèle n'existe pas ; le score d'un jeton est une fonction fixe du préfixe et du jeton (crc32). Le modèle oracle puis A0 la remplaceront.
  - T11 en 4 processus au plus : à 12 processus, `make test` a été arrêté faute de mémoire.
  - V provisoire : mots des synthèses de référence du dossier (comme T4, T5).
- **Écarts avec SPEC.md :** aucun de plus. `make test` passe de 171 s à 552 s (T11).
- **Suite prévue :** modèle oracle, `ccm answer --oracle` de bout en bout (recherche, anonymiseur, oracle, vérificateur, relance après NOTE_*).

## 2026-10-29 — Phase 3 — Modèle oracle, `ccm answer --oracle` de bout en bout
- **Travail fait :** tâche donnée par Raphael : modèle oracle, `ccm answer --oracle` de bout en bout, tests figés dans `tests/golden/`, aucun nom, nombre ou date affiché hors du contexte, démo filmable.
  - `ccm/model/oracle.py` : l'oracle lit la vérité terrain du dossier (`verite.json`, `questions.json`) et rejoue la suite de référence (`cible_de_reference`) dans le **vrai** contexte : lignes du stock ingéré (texte exact, copie gardée du groupe de doublons), message lu par les vrais détecteurs, exemple de l'anonymiseur. Si une ligne ou un fait de la référence manque au contexte, ou si l'automate refuse la suite, il s'abstient (ABSTENTION FIN) et dit pourquoi. Relance : la suite reprend après NOTE_SAME / NOTE_DIFF.
  - `ccm/answer.py` (`repondre`) : lecture du message, recherche (trace), anonymiseur, oracle, vérificateur, une relance après une contrainte notée.
  - `ccm answer [QUESTION] --stock S --oracle DOSSIER [--id ID] [--synthese] [--conv C] [--suite]`.
  - `cible_de_reference` : paramètres `lignes` et `msg` (stock de référence par défaut, inchangé) ; un fait absent lève KeyError (StopIteration dans un générateur devenait RuntimeError).
  - Contrôle du rendu fermé de T5 déplacé dans `ccm/eval/rendu.py` (`fermes`, `controler`), partagé par T5, T11 et les tests figés ; T5 et T11 inchangés sur le fond.
  - `tests/golden/test_answer_oracle.py` : dossier de validation figé `tests/golden/oracle/syn-1000000` (9 PDF, 404 Ko), ingéré par la vraie chaîne ; 40 questions × 2 modes : pas du modèle, abstentions et texte égaux à `oracle/attendu.json` ; chaque fragment contrôlé comme T5. Plus 3 appels de la commande `ccm answer` (calcul, NOTE_DIFF avec relance, synthèse). Réécriture : `CCM_GOLDEN=ecrire`.
  - `demo/demo.py` : 9 scènes sur le dossier figé (deux étapes, calcul exact, conflit, identité par ressemblance, dialogue, déclaration et relance, ASK_SAME, abstention, synthèse), avec la question vue par le modèle (marques, aucun nom ni nombre), ses pas, la réponse vérifiée. `--pause` pour filmer.
- **Mesures :** oracle sur 10 dossiers de validation (`syn-1000001` à `syn-1000010`), citation et synthèse : **740 / 802 réponses rejouées (92,3 %)**, 0 erreur du vérificateur. 62 abstentions de l'oracle : 58 faits non détectés par la vraie détection (surtout en synthèse, qui pointe plus de noms), 2 lignes hors du contexte rendu par la recherche, 2 refus de l'automate (`syn-1000009-q20` : `M:19.2` refusé à l'état M2, pas encore analysé). Dossier figé : 76 / 80. Tests figés : 2 passés, déterministes (deux passes égales). `make test` complet : 288 passés, 1 échec (sonde T5 `fragment_etranger[autre]` : `controler` lève AssertionError et non plus `pytest.fail`) ; sonde corrigée, les 7 sondes repassent. Second `make test` complet arrêté par manque de mémoire ; relancé en deux parties : lint OK, 288 passés hors T11, T11 : 1 passé (100 000 décodages). Tout passe.
- **Décisions :**
  - Dossier figé pris dans la validation (jamais dans le test) ; ses sorties attendues sont celles de la chaîne actuelle, relues (pas de vérité réglée pour passer).
  - Sans `--conv`, `ccm answer` tire un identifiant de conversation neuf (les contraintes notées valent pour cette conversation).
  - V (mots libres de la synthèse) : provisoire, mots des synthèses de référence du dossier (comme T4, T5, T11).
  - Seuil interne du test figé : au moins 90 % des réponses rejouées sans abstention de l'oracle (mesure, pas un seuil de SPEC).
- **Écarts avec SPEC.md :** `ccm/answer.py` et `demo/` ne sont pas dans l'arbre de §3 (orchestration de la chaîne, démo). Observation : « Il ressort de nos constatations… », « Il est établi que… » reçoivent DEPEND_DE vers la phrase précédente (mot « Il » de la liste de SPEC §5, étape 3) ; le vérificateur affiche donc cette phrase en « Contexte : » (§11, étape 2), même quand elle parle d'un autre événement (démo, scènes 1, 5, 6). Conforme à SPEC, et dans les textes permis par T5 (dépendances) : pas une fuite. Question pour Raphael : exclure les « il » impersonnels (« Il ressort », « Il est établi », « Il apparaît ») de la liste ?
- **Suite prévue :** les trois seuils de phase 3 semblent atteints (suites de référence 100 %, 100 925 décodages valides, rendu fermé contrôlé) : `reports/phase-3.md` et relecture avec Raphael avant `phase-3-ok` et la fusion (ne pas étiqueter sans son accord).

## 2026-10-30 — Phase 3 — `anonymize.encode` (§8)
- **Travail fait :** tâche donnée par Raphael. `ccm/anonymize/encode.py` : `encode(ex, voc, decouper, ctx=, gcfg=)` → `Encodage` (toutes les tables de §8) ; `Vocabulaire` (jetons spéciaux par variante, identifiants après ceux du tokenizer) ; `masque_pas` (pas permis → vecteur, servira au décodage). `ModelConfig` : `variante`, `t_max`, `p_max`, `s_max`, `rel_max` ; `anonymiseur.unites_max` = 16. Tests écrits avant le code : `tests/unit/test_encode.py` ; T2 étendu à l'encodage entier (B : tables égales sans mise en ordre ; A0 : après mise en ordre), résultat attendu inchangé.
- **Mesures :** 40 dossiers d'entraînement, 1 596 exemples à 150 propositions, A0, tokenizer de test (un jeton par mot : T n'est qu'un ordre de grandeur) : T 1 017 à 2 301, M 89 à 213, K 47 à 128, S 2 à 14, triplets 27 à 78 (la coupe à 200 n'est jamais atteinte) ; chaque pas de référence est dans son masque. Lint OK. **`make test` complet non terminé** : arrêté par le système, faute de mémoire. Passés seulement : encode, T2, anonymiseur, config, T7. Non relancés : T5, T9, T11, tests figés et le reste.
- **Décisions :**
  - Tokenizer passé en paramètre (`decouper`) : ni BPE (phase 5) ni tokenizer de base (phase 4) n'existent encore.
  - [SORTIE] est en segment 2 ; [REL] en segment 1 ; [BOS] en segment 0.
  - Héritage : un pointeur copie **tous** les indices de sa position cible (`prop_idx`, `name_idx`, `val_idx`, `num_attr`) : [/P] pour P, le slot pour M et N. Une mention d'une proposition donne donc aussi `prop_idx`.
  - Pointeurs : trois jetons ⟨PT:P⟩ ⟨PT:N⟩ ⟨PT:M⟩ (« vecteur du genre », §9).
  - Réservoir des valeurs en A : jetons ⟨NUM_i⟩ et ⟨DATE_i⟩, i = `valeur_id` ; aucune table de plus (512 vecteurs en plus des 1 280).
  - `num_attr` a 4 colonnes et §6 demande la précision d'une date : elle occupe la colonne unité (cases 18 à 20). Une unité vide ou inconnue va dans « autre » (17) ; 12 unités en config sur 16 cases.
  - Espace de sortie : L = 30 dès le mode citation (jetons de synthèse masqués), pour garder les mêmes indices en phase 4 bis.
  - [DEPEND] : sur la proposition qui dépend (a de (a, b)), pas sur b. [CONFLIT] : sur les deux.
  - [REL] : triplets triés par ordre d'apparition puis identifiant, coupés à `rel_max` ; indépendant du tirage. ⟨R:nom⟩ : 10 jetons (un par relation, le sens est donné par l'ordre a, b).
  - Limites dépassées : erreur, aucune coupe silencieuse.
- **Écarts avec SPEC.md :** synthèse hors de `encode` : `Exemple.cible` refuse `W:` et S ≤ 96 ; à reprendre en phase 4 bis. Observation : la cible de l'exemple de §4 (`P:0 SAME …`) n'avait pas de connecteur, l'automate la refusait (§10). **Corrigé avec l'accord de Raphael le 2026-10-30** : `P:0 ET SAME …` dans SPEC.md §4 et `tests/golden/exemple_spec.json` ; aucune règle changée ; `SAME` reste un segment, pas un connecteur.
- **Phase :** `encode` n'est pas un livrable de la phase 3 (§2), mais du code `anonymize` sans poids ni GPU. Tâche demandée explicitement ; la phase 3 reste non close (`reports/phase-3.md` non écrit) et la phase 4 n'est pas ouverte.
- **Suite prévue :** `reports/phase-3.md` et relecture avec Raphael, avec `make test-complet` avant la clôture.

## 2026-10-30 — Phase 3 — T11 hors de `make test`
- **Travail fait :** demande de Raphael, `make test` s'arrêtant faute de mémoire. Marque pytest `couteux` sur T11, exclue par défaut (`addopts`). `make test` : lint et pytest sans T11 ; `make test-t11` : T11 seul ; `make test-complet` : les deux, en deux processus l'un après l'autre. CI : `make test-complet`, car SPEC §10 bis place T11 en CI. T11 lui-même n'est pas modifié (mêmes 100 000 décodages, mêmes contrôles). `CLAUDE.md` et `README.md` mis à jour.
- **Mesures :** nouveau `make test` : lint OK, **310 passés, 1 désélectionné (T11)**, 179 s (552 s avec T11 le 2026-10-28), sans arrêt mémoire. Sélection de `-m couteux` et `make -n test-complet` contrôlés, sans les exécuter. T11 n'a pas tourné depuis `encode` ; aucun code qu'il lit n'a changé, seulement `configs/ingest.yaml` (`unites_max`, nouvelle clé) ; la CI le lancera.
- **Décisions :** `make test-complet` obligatoire si le travail touche `grammar`, `verify`, `anonymize` (hors `encode`), `ingest` ou `worldgen`, et avant de clore une phase. Un `pytest` nu exclut aussi T11 ; un chemin explicite vers son fichier le désélectionne : passer par `make test-t11` ou `-m couteux`.
- **Écarts avec SPEC.md :** aucun : T11 reste en CI.
- **Suite prévue :** celle de l'entrée précédente.

## 2026-10-31 — Phase 3 — Jeux publics de réglage fin (§12) : téléchargement, licences, conversion arrêtée
- **Tailles (en-tête `Content-Length`, requêtes HEAD, avant tout téléchargement) :**
  - HotpotQA, réglage « distracteurs » (Parquet, `hotpotqa/hotpot_qa`, révision `1908d6af`) : `train-00000-of-00002` 165 624 177 ; `train-00001-of-00002` 166 162 479 ; `validation-00000-of-00001` 27 452 575. L'hôte d'origine (`curtis.ml.cmu.edu`, JSON) ne résout plus.
  - PIAF v1.2 (`piaf-v1.2.json`, data.gouv) : 4 744 747.
  - SQuAD 2.0 : `train-v2.0.json` 42 123 633 ; `dev-v2.0.json` 4 370 528.
  - FinQA : `train.json` 78 216 616 ; `dev.json` 10 954 658 ; `test.json` 14 395 143 ; `LICENSE` 1 067.
  - TAB : `echr_train.json` 47 503 662 ; `echr_dev.json` 12 643 092 ; `echr_test.json` 13 103 290 ; `LICENSE.txt` 1 089.
  - FQuAD : taille inconnue (HTTP 401 sur `illuin/fquad`, `fquad.illuin.tech` ne résout pas).
  - **Total : 587 296 756 octets (0,587 Go), PIAF compris**, pour environ 1 Go attendu. Écart surtout dû à HotpotQA en Parquet compressé (0,36 Go) plutôt qu'en JSON.
- **Travail fait :** demande de Raphael : télécharger et convertir les jeux publics du §12. Sur `phase-3` (non close ; phase 4 non ouverte). `ccm jeux` (`ccm/data/jeux.py`, versions et SHA-256 figés), `ccm convertir` (`ccm/data/publics.py`, `hotpot.py`, `squad_fr.py`, `finqa.py`), `configs/donnees.yaml`, `tests/unit/test_donnees_publiques.py`. Données dans `D:/Nunda-donnees/` (`brut/`, `converti/`, `cache-zones.sqlite`, `conversion.log`). `uv`, `make`, `.venv` (5,1 Go) et `runs/modeles` (1,1 Go) installés : ils manquaient sur cette machine.
- **ARRÊT : cas 3 (PIAF), licence pas claire.** data.gouv : « License Not Specified » ; Hugging Face : étiquette MIT, section licence vide ; article LREC 2020 : « CC-BY-SA ». PIAF n'est ni téléchargé ni converti.
- **Mesures :**
  - **Téléchargés (0,582 Go, tailles égales aux `Content-Length`, SHA-256 figés) :** HotpotQA, SQuAD 2.0, FinQA, TAB.
  - **FQuAD sauté :** pas d'accès (HTTP 401 sur `illuin/fquad`, `fquad.illuin.tech` ne résout pas). Aucun miroir utilisé. Licence non lue.
  - **SQuAD converti, mais inutilisable :** 48 712 exemples écrits sur 49 443 questions sans réponse (731 rejetés, titre d'article resté en clair).
  - **FinQA et HotpotQA non convertis.** Claude Code a arrêté la conversion pour manque de mémoire pendant la détection de FinQA ; pas relancée. Le cache garde 183 237 textes détectés et sert à la reprise. Essai sur 300 questions par partie, avant l'ajout du rejet des titres, supprimé ensuite : HotpotQA 600 gardées sur 600 (29 titres sur 5 941 restés en clair). FinQA à 300 questions : cibles lues et correctes sur 3 exemples, bilan non relu.
  - **Détection sur l'anglais (cache) :** SQuAD 53,4 % des questions écrites entièrement masquées ; caractères masqués : SQuAD 74,9 % (questions), 40,2 % (phrases) ; HotpotQA 63,2 % et 55,0 %, sur 300 questions. Sans les zones de spaCy seul : 42,8 %, 30,1 %, 55,9 %, 47,7 %. **FinQA (`dev`) : 0 caractère masqué** sur 661 questions et 7 325 phrases : le texte est en minuscules et une zone sans majuscule n'est pas gardée (§6), donc tout nom y resterait en clair.
  - Débit de la détection : 123 textes/s avec `lot` 32, sur 12 277 textes, chargement compris. `lot_gliner` 128 non mesuré à part.
  - `make test` : 324 passés, 1 ignoré, 1 désélectionné (T11). `make test-complet` non lancé : aucun module de sa liste touché (`ner/propagate.py` : paramètre `zones` facultatif).
- **Décisions :**
  - HotpotQA vient du Parquet de `hotpotqa/hotpot_qa`, l'hôte d'origine ne résolvant plus.
  - TAB : aucune conversion (§12), fichiers bruts seulement, jamais en entraînement.
  - Anglais : `nombres_en` dans `data/publics.py`, car `ingest.numbers` lit « 5,829 » comme 5,829. Colonne `valeurs` à côté de `exemple` dans le Parquet (nombres seulement, pour le masque).
  - Un exemple dont le texte contient encore un titre d'article est rejeté (§15). Cela ne prouve pas l'absence d'autres noms.
  - `squad` converti laissé sur le disque, avec `A_NE_PAS_UTILISER.txt`.
- **Écarts avec SPEC.md :** conversion demandée non terminée. PIAF et FQuAD absents : plus aucune source de citation en français (poids 15 %). Total réel 0,587 Go pour environ 1 Go attendu.
- **Questions pour Raphael :**
  1. PIAF : quelle licence retenir ? Proposition : traiter comme CC BY-SA (la plus stricte déclarée par les auteurs) après confirmation d'Etalab.
  2. Détection sur l'anglais : §6 ne la prévoit pas. Proposition : GLiNER et règles seuls pour `en`, sans spaCy français ni D4, mesurés sur TAB avant toute reconversion.
  3. FinQA en minuscules : garder le jeu (noms en clair, contraire au §15), ou chercher une autre détection ?
  4. CC BY-SA 4.0 (HotpotQA, SQuAD) : le partage à l'identique est-il compatible avec des poids ouverts sous une autre licence ?
- **Suite prévue :** selon les réponses ; reprise avec `ccm convertir finqa`, puis `ccm convertir hotpot`, sous surveillance de la mémoire. `reports/phase-3.md` reste à écrire.

## 2026-10-31 — Phase 3 — Jeux publics du §12 : conversion terminée (sauf FQuAD)

- **Travail fait :** suite de l'entrée précédente, dont les questions sont tranchées. PIAF téléchargé et ajouté à `ccm/data/jeux.py`. Chaînes de détection par jeu, cache par chaîne. `ccm/eval/tab.py` (mesure sur TAB `dev`). `detecter_minuscules` pour FinQA. `convertir_partie` par paquets, pour la mémoire. SQuAD, HotpotQA, FinQA et PIAF reconvertis ; `squad` de la première passe remplacé. Sur `phase-3` (non close ; phase 4 non ouverte).
- **Décisions de Raphael :**
  - PIAF : CC BY-SA retenue (`DATA_LICENSES.md`).
  - Anglais : GLiNER, règles, puis D4 ajouté après mesure ; pas de spaCy français.
  - FinQA : chercher une autre détection, retirer le jeu si ce n'est pas satisfaisant. Résultat : gardé, voir mesures.
  - CC BY-SA et poids ouverts : Raphael ne sait pas. **Question ouverte, à trancher avant toute publication de poids.**
- **Mesures, conversion :**
  - SQuAD : 46 428 gardés sur 49 443 (6,1 % de rejets, tous de titre ; 11 % sans D4).
  - HotpotQA : 59 733 sur 97 852 (train 55 125, validation 4 608). **Rejets 39,0 %** : 38 096 titres restés en clair, 23 justificatives hors du contexte.
  - FinQA : 6 086 sur 6 489 (train 4 606, validation 628, test 852, partie `test` jamais pour entraîner). Écartés par la règle du §12 avant conversion : 2 792.
  - PIAF : 9 224 sur 9 224, 0 rejet.
  - TAB : aucune conversion (§12). FQuAD : toujours sans accès, licence non lue, aucun miroir.
  - Débit de la détection anglaise : environ 360 textes/s (1,9 M textes en 87 min, `lot_gliner` 128).
- **Mesures, TAB `dev`, rappel PERSON / ORG / LOC et caractères masqués :**
  - 4 détecteurs : 0,969 / 0,920 / 0,985 ; 44,6 %.
  - GLiNER + règles : 0,919 / 0,826 / 0,940 ; 14,0 %.
  - **+ D4 (retenu, anglais) : 0,934 / 0,857 / 0,972 ; 16,5 %.**
  - Minuscules, seuil 0,6 : 0,907 / 0,792 / 0,925 ; 18,2 % (FinQA 8,7 %).
  - **Minuscules, seuil 0,3 (retenu, FinQA) : 0,943 / 0,902 / 0,949 ; 23,7 % (FinQA 14,6 %).**
  - Critères fixés avant mesure : PER ≥ 0,87 et masquage réduit (anglais) ; PER et ORG ≥ 0,87 sur TAB en minuscules et moins de 25 % masqués sur FinQA (FinQA gardé). TAB n'est pas financier : le rappel sur FinQA reste indirect.
- **Contrôle du masquage** (échantillons de 3 000 questions pour la part masquée, 2 000 exemples convertis pour le reste ; script hors dépôt) :
  - Caractères masqués, questions / phrases : SQuAD 14,3 / 15,6 % ; HotpotQA 25,5 / 24,7 % ; FinQA 11,3 / 14,6 % ; PIAF 13,5 / 15,2 %. **PIAF n'est pas sur-masqué** : son zéro rejet de titre ne vient pas de là.
  - Mots à majuscule en milieu de phrase restés dans les exemples, pour 1 000 mots : SQuAD 21,0 ; HotpotQA 27,6 ; PIAF 0,5 ; FinQA 0,0 (en minuscules : ne prouve rien). Indice seulement : tous ne sont pas des noms.
  - **HotpotQA : 10,3 % des exemples gardés contiennent un titre à plusieurs mots d'un autre article** (SQuAD 2,1 %), repéré parmi les titres de 3 000 questions seulement : c'est un minimum. Le rejet ne contrôle que les titres de la question elle-même.
  - Rejets de titre HotpotQA, sur 3 000 questions : 1 199 rejets, 2 002 titres. 1 953 (97,5 %) ne contiennent que des mots courants (« Wildfire », « Hip hop », « Picture to Burn »), que D4 ne peut pas voir ; 34 ne sont trouvés qu'à l'intérieur d'un autre mot. Beaucoup ne sont pas des noms de personne ; proportion non mesurée.
- **Décisions :**
  - Rejet de titre gardé tel quel, malgré 39 % de rejets : l'assouplir laisserait passer plus de noms. Conséquence : perte de questions sur des titres de mots courants.
  - Chaîne anglaise `[gliner, regle, majuscules]` et seuil FinQA 0,3 dans `configs/donnees.yaml`, propres aux jeux publics. Rien ne change dans la configuration d'ingestion.
- **Écarts avec SPEC.md :**
  - **§15 « aucune chaîne de nom dans un fichier d'entraînement » : non tenue strictement sur ces jeux réels.** Sur TAB, environ 6,6 % des personnes et 14 % des organisations restent en clair (anglais), 5,7 % et 10 % en minuscules. Le contrôle ci-dessus le confirme sur HotpotQA. **À trancher par Raphael avant tout entraînement sur ces jeux (phase 4).**
  - §6 ne prévoit pas de chaîne anglaise distincte (D2 retiré pour `en`) ; `nombres_en` et colonne `valeurs` en plus.
  - FQuAD absent : PIAF seul pour la citation en français (poids 15 %), 9 224 questions.
  - HotpotQA ramené à 59 733 questions.
- **Incidents :** Claude Code a arrêté la conversion de HotpotQA pour manque de mémoire vers 17 h 45, avec 3,4 Go libres. Le processus de conversion avait survécu à cet arrêt (15,4 Go) : tué à la main, cache intact. Relancée à la demande de Raphael, autres applications fermées, sans incident. Origine des 15 Go non cherchée.
- **Tests :** `make test` : 325 passés, 1 ignoré, 1 désélectionné (T11). `ruff format --check` propre. `make test-complet` non lancé : aucun module de sa liste touché depuis la première passe.
- **Pistes, à ne pas lancer sans demande (Raphael) :**
  - Mesurer `urchade/gliner_multi_pii-v1` (Apache 2.0, licence vue sur sa page) sur TAB `dev`, en texte normal et en minuscules, à la place de GLiNER puis en plus.
  - Mesurer `Jean-Baptiste/camembert-ner` (MIT, vue sur sa page). Français seul : TAB ne convient pas ; référence : corpus synthétique, partie validation, à regénérer (`ccm corpus`). Le rappel PER y est déjà de 0,998 : la mesure dira surtout s'il masque trop.
  - Seuil proposé sur TAB, à confirmer avant la mesure : au moins la moitié des personnes et organisations restantes en moins, et 25 % de caractères masqués au plus. Aucun modèle n'entre dans la chaîne sans accord de Raphael (§6).
  - LLM écarté par Raphael.
  - FinQA : à comparer avec et sans en phase 4 (5 % du poids, le plus exposé aux noms).
- **Questions pour Raphael :**
  1. §15 : quel reste de noms accepter sur les jeux publics, avant la phase 4 ?
  2. CC BY-SA 4.0 et poids ouverts.
  3. §16 : pré-entraînement bilingue 70/30, ou français seul avec HotpotQA traduit.
- **Suite prévue :** Raphael prévoit de télécharger le droit français (Légifrance, Judilibre, phases 4 et 5). Avant cela : lire les licences et le cadre de réutilisation des décisions de justice (vraies personnes). `reports/phase-3.md` reste à écrire ; rien à entraîner avant la clôture de la phase 3.

## 2026-10-31 — Phase 3 — Décisions de Raphael : noms, langue, poids ; recherche sur les licences

- **Décisions de Raphael :**
  - **Noms : on n'en veut pas, à réduire au maximum, quitte à décaler le plan.**
  - **Langue : français.** §16 coché. La traduction de HotpotQA n'est pas décidée (voir ci-dessous).
  - **Poids : préférence pour des poids fermés**, pour le levier commercial. Cela remplace « code fermé, poids ouverts » (2026-10-18, §3). §16 mis à jour, case laissée ouverte.
  - Recherche sur les licences confiée à l'agent.
- **Recherche (synthèse, pas un avis juridique) :**
  - **Creative Commons** (page « Using CC-licensed works for AI training », lue) : la licence ne s'applique que si une permission est nécessaire ; une exception au droit d'auteur l'écarte. Le partage à l'identique ne joue que si le modèle ou ses sorties sont **partagés publiquement**, et CC conseille alors la même licence.
  - **Exception de fouille de textes** (directive 2019/790 art. 4, art. L122-5-3 CPI ; extraits lus) : usage commercial possible, sauf opposition du titulaire. Son articulation avec le partage à l'identique reste débattue (Szkalej et Senftleben, JIPITEC, résumé lu seulement).
  - **Conséquence :** des poids jamais distribués ne déclenchent pas le partage à l'identique selon CC. **Installer les poids chez un client est une distribution**, et le §3 vise un produit hors ligne : c'est là qu'est le risque. Une traduction est une adaptation : HotpotQA traduit reste CC BY-SA.
  - **Légifrance :** Licence Ouverte 2.0, conditions de PISTE et de l'API (page Open data lue ; ces conditions non lues). Licence ouverte : réutilisation commerciale permise, avec mention de la source.
  - **Judilibre :** Licence Ouverte 2.0 complétée par des CGU (V8, lues par extraits, pas en entier). **Trois réserves :** interdiction d'altérer les données ; juridiction, formation, siège et date à mentionner pour chaque décision, sans pouvoir les en détacher ; réutilisateur responsable de traitement, tenu de garder ses données à jour. Masquer et découper les décisions pour l'entraînement peut heurter les deux premières : **pas clair, à faire valider avant de s'en servir** (cas d'arrêt 3 si cela reste flou).
  - **Art. L111-13 COJ (lu) :** interdiction, sous peine pénale, de réutiliser l'identité des magistrats et des greffiers pour évaluer, analyser, comparer ou prédire leurs pratiques. Noms des parties et des tiers occultés à la source, ce qui ne garantit pas qu'il n'en reste aucun.
- **Recommandation de l'agent, non décidée :** poids fermés et français vont ensemble si le modèle commercial n'utilise aucune donnée CC BY-SA : retirer HotpotQA (traduit ou non), SQuAD, PIAF et Wikipédia. Le plus prudent ; un juriste peut assouplir. Sources restantes : corpus synthétique, Légifrance, Judilibre selon la validation, textes de l'Union européenne (licence à lire), livres du domaine public. Prix : plus de citation humaine annotée sur texte réel ; les chaînes et l'abstention reposeraient sur le synthétique et le modèle enseignant.
- **Écarts avec SPEC.md :** le §12 (sources, poids) et le §1 C7 ne correspondent plus à la décision de langue ; non modifiés, en attente des arbitrages de Raphael. Les conversions anglaises de ce jour ne serviront sans doute pas à l'entraînement ; TAB reste utile pour la mesure.
- **Plan pour les noms, à ne pas lancer sans demande :** mesurer `gliner_multi_pii-v1` et `camembert-ner` (entrée précédente) ; trouver une référence française réelle annotée, car 0,998 ne vaut que sur des noms synthétiques ; proposer la liste Wikidata des humains (déjà téléchargée, CC0) comme détecteur supplémentaire, ce qui change le §6 ; élargir le contrôle des exemples au-delà des titres de la question. JORF : nominations et décorations pleines de vrais noms, à surveiller.
- **Tests :** `make test` non relancé : texte seul, aucun code touché.
- **Questions pour Raphael :** 1. Retirer les données CC BY-SA du modèle commercial ? 2. Consulter un juriste pour Judilibre et les poids distribués ?
- **Suite prévue :** selon les réponses. Avant tout téléchargement du droit français : lire en entier les CGU de Judilibre, de PISTE et de l'API Légifrance. `reports/phase-3.md` reste à écrire ; rien à entraîner avant la clôture de la phase 3.

## 2026-11-01 — Phase 3 — Droit français : Légifrance et Judilibre découpés en propositions
- **Travail fait :** demande de Raphael. `ccm jeux` connaît le stock LEGI (SHA-256 figé). `ccm legi` (`ccm/data/legi.py`) lit l'archive en flux (`tarfile` `r|gz`), sans rien écrire sur le disque. `ccm judilibre` (`ccm/data/judilibre.py`) : `/scan` jour par jour, jeton OAuth, reprise par mois. `ccm/data/droit.py` écrit les textes dans le stock ; `segmenter_paragraphes`, extrait de `segmenter`, donne la même découpe que pour les PDF. `tests/unit/test_droit.py`.
- **Taille sur le disque, Légifrance :**
  - Archive `D:/Nunda-donnees/brut/legi/Freemium_legi_global_20250713-140000.tar.gz` : **1 171 027 316 octets** (égale au `Content-Length`). Aucun fichier décompressé : un seul fichier dans le dossier.
  - Base `D:/Nunda-donnees/droit.sqlite` après Légifrance : 305 360 896 octets.
- **Mesures, Légifrance :** 5 253 903 membres lus ; sous `code_en_vigueur` : **161 302 articles gardés**, 327 600 écartés (autre état que VIGUEUR), 4 écartés (état VIGUEUR, date du dump hors de leur période). **926 489 propositions** : PHRASE 702 358, EN_TETE 161 338, LIGNE_TABLEAU 50 483, CHAMP 9 632, PARTIE 2 678. 78 codes. Contrôle : `Code civil, article 1240` donne son en-tête et une phrase, le texte attendu. Durée 11 min 38 au dernier passage, 21 min au plus selon la charge de la machine, 6 processus.
- **Judilibre, téléchargé :** **36 876 décisions** (Cour de cassation 22 349, cours d'appel 14 527), toutes distinctes, toutes datées du mois demandé, aucun texte vide. 186 fichiers mensuels, 101 min, aucune erreur ni 429. Taille sur le disque : `D:/Nunda-donnees/brut/judilibre` **88 174 890 octets**.
- **Quotas :** en-tête `x-rate-limit` lu : 20 appels environ sur la fenêtre courte, 1 million environ sur la longue. Pause de 0,2 s, soit 5 appels par seconde au plus. L'accès 403 a été levé quand Raphael a rattaché Judilibre (production) à l'application.
- **Reprise, essai réel :** `ccm judilibre` relancé : aucun mois redemandé, `deja_la` 36 876, 0 ajout, 22 s.
- **Base finale `D:/Nunda-donnees/droit.sqlite` : 1 030 590 464 octets, 3 193 579 propositions** sur 198 178 pièces. Décisions : **2 267 090 propositions** (PHRASE 1 708 411, PARTIE 481 307, CHAMP 40 471, EN_TETE 36 901), découpe en 9 min 11. Chaque décision commence par son en-tête d'identification ; 25 autres EN_TETE sont des lignes de capitales du texte lui-même. Aucune proposition vide, aucune pièce sans proposition, aucune entité restante.
- **Taille totale sur le disque : 2 289 792 670 octets** (archive 1 171 027 316, décisions 88 174 890, base 1 030 590 464).
- **Reste imparfait, non corrigé :** 36 599 propositions de décisions sans lettre (1,6 %), dont 29 178 sans chiffre non plus, et 7 170 dans Légifrance : apostrophe ou « » » fermant une citation, `***`, numéros, 2 880 « . » seuls. 1 305 propositions de décisions dépassaient 2 000 caractères à la première découpe, non recompté. Le texte des décisions montre aussi `?` à la place de `€` : c'est la source, non modifiée.
- **Première découpe, remplacée :** base de 1 073 455 104 octets, 2 575 106 propositions pour les décisions, dont **210 373 sans lettre** (8 %), 164 544 « . » seuls et 243 002 `&apos;`. Deux défauts corrigés (commit `971eff8`) :
  - `segment.py` masquait le premier point de « X... » comme une initiale ; la phrase se coupait en « M. X.. », « . », suite. Ce code sert aussi aux PDF : les stocks d'ingestion déjà construits gardent ce défaut là où ils contiennent « X... ». Sur quatre mois de décisions : 759 points seuls avant, 27 après.
  - `net` ne décodait pas les entités HTML.
- **Reconstruction :** une première tentative a été arrêtée par le système à 18 h 18, mémoire presque épuisée, à 130 000 articles sur 161 302. Relancée à la demande de Raphael depuis une base vide et les fichiers déjà sur le disque, sans appel réseau : terminée. L'ancienne base est effacée.
- **Décisions :**
  - **Une pièce par article ou décision**, avec une proposition EN_TETE d'identification (`Code civil, article 1240` ; juridiction, formation, siège et date pour une décision, art. V des CGU). Type LOI (rang 1) pour les articles, AUTRE pour les décisions.
  - **Découpe seule** : ni noms, ni nombres, ni doublons, ni conflits, ni index BM25. Ils relèvent de la chaîne du §12. Conséquence : `droit.sqlite` contient le texte brut, dont des noms réels ; c'est une base de travail, pas un fichier d'entraînement.
  - **Échantillon Judilibre :** Cour de cassation depuis 2016-01, cours d'appel depuis 2022-01, jusqu'à 2026-09 ; part égale par mois (50 000 ÷ 186 fenêtres = 268). Un appel par jour, car l'API trie par date ; un jour vide reporte sur les suivants. Dans un jour : les premières décisions rendues par l'API. Un mois pauvre n'est pas compensé : **36 876 décisions, pas 50 000** (mois de 18 à 268 décisions). Le plafond était « au plus ».
  - Identifiants dans `D:/Nunda-donnees/piste-identifiants.txt`, hors de git.
- **Écarts avec SPEC.md :**
  - **Le droit est figé au 2025-07-13**, date du dernier stock publié par la DILA : « en vigueur » veut dire en vigueur à cette date, soit 16 mois de retard. Les 484 mises à jour quotidiennes (environ 3,1 Go) ne sont pas appliquées.
  - JORF non téléchargé à part (§12 le cite pour le pré-entraînement) ; pas demandé.
  - CGU : lues en partie seulement, contrairement à la suite prévue plus haut. Cour de cassation V8 : articles V, VI, VII, IX, XI C à E, XII et XIII. PISTE : pages 3 à 6 sur 8. API Légifrance non lues : cette API n'est pas utilisée.
- **À signaler seulement si l'échantillon sert à publier ou à vendre :** CGU art. V, obligation de tenir ses données à jour (72 h recommandées) ; un échantillon figé ne la remplit pas.
- **Incident :** la clé d'API de Raphael s'est affichée dans la session de travail. Elle n'est pas utilisée, n'est pas dans le dépôt, et le fichier qui la portait est supprimé. À régénérer sur PISTE.
- **Tests :** `make test-complet` sur le code final : 341 passés, 1 ignoré, 1 désélectionné ; T11 passé.
- **Suite prévue :** la dernière « Suite prévue » de phase 3 reste ouverte : `reports/phase-3.md`, et les arbitrages de langue et de licence demandés à Raphael. La chaîne du §12 (noms, nombres, doublons, conflits, BM25) n'est pas lancée sur `droit.sqlite`.

## 2026-11-02 — Phase 3 (§16, préparation de la phase 4) — Enseignant 7B local : Qwen retenu
- **Travail fait :** llama.cpp b12048 (CUDA 12.4) installé dans `D:/Nunda-donnees/llama.cpp/b12048/`, empreintes GitHub contrôlées. Qwen2.5-7B-Instruct et Mistral-7B-Instruct-v0.3 téléchargés en Q4_K_M dans `D:/Nunda-donnees/modeles/enseignant/`, SHA-256 identiques à ceux de Hugging Face. `uv run ccm enseignant` (`ccm/data/enseignant.py`) lance les deux modèles sur 10 articles de Légifrance : même prompt, température 0, JSON imposé par schéma, puis second passage du §12. Résultats : `D:/Nunda-donnees/enseignant/comparaison.json`, avec les sorties complètes.
- **Mesures, 10 articles** (tirés avec la graine 20261102 parmi les 54 012 articles de 3 à 8 phrases et de 400 à 1 800 caractères) :

  | | Qwen2.5-7B Q4_K_M | Mistral-7B v0.3 Q4_K_M |
  | --- | --- | --- |
  | Le modèle répond, JSON valide | 10/10 | 10/10 |
  | Couches sur le GPU | 29/29 | 33/33 |
  | VRAM au pic, sur 24 576 Mio (contexte 8 192) | 5 050 Mio | 5 530 Mio |
  | Débit | 103 jetons/s | 109 jetons/s |
  | Gardées par les règles du §12 | 6/10 | 4/10 |
  | Rejets : plus de 4 justificatives | 1 | 0 |
  | Rejets : « réponse possible » sans les justificatives | 2 | 6 |
  | Rejets : « pas de réponse » avec les justificatives | 1 | 0 |
  | Lecture de l'agent : question bonne (voir ci-dessous) | 6/10 (n° 1, 2, 3, 8, 9, 10) | 2/10 (n° 4, 5) |
  | Parmi les gardées : bonnes selon cette lecture | 5/6 | 0/4 |
  | Fautes de français | 0 | 2 (n° 9 « Quels sont les règles », n° 10 « peut dispensé ») |

  Deuxième exécution : sorties identiques pour les deux modèles. La VRAM est le pic relevé après chaque article, pas un suivi continu.
- **Décisions :**
  - **Enseignant retenu : Qwen2.5-7B-Instruct, Q4_K_M, servi par llama.cpp.** Il garde plus d'exemples, et ceux qu'il garde sont meilleurs. Les réponses des deux modèles et la mémoire ne départagent pas : les deux tiennent largement dans 24 Go.
  - **Confirmé par Raphael le 2026-11-02 : on garde Qwen.**
  - **Ce choix renverse celui du 2026-10-18** (« Mistral, meilleur en français », et un modèle de 12B ou 24B envisagé). Sur ces 10 articles, Mistral 7B ne fait pas mieux en français. Nemo 12B et Small 24B n'ont pas été testés.
  - **llama.cpp plutôt que vLLM :** vLLM n'est pas pris en charge sous Windows natif, il aurait fallu WSL ou Docker. Q4_K_M donne bien 4 bits, sans étape de plus.
  - **Mistral 7B :** pas de GGUF officiel trouvé, quantification communautaire de `bartowski`. Qwen vient du dépôt officiel.
- **Limites de la comparaison :**
  - **Échantillon de 10 articles : indice, pas preuve.** Un seul prompt, non réglé. L'écart de 6 contre 4 aux règles du §12 tient à deux articles.
  - **La « lecture de l'agent » est un jugement d'une seule personne, sans aveugle** : l'agent savait quel modèle avait écrit quoi. Critère : réponse présente dans les justificatives, jeu de justificatives juste, rien d'inventé, français correct. Cas limites comptés bons ou mauvais par ce critère : n° 8 de Mistral compté non bon (justificative 6 superflue, contenu juste), n° 6 de Qwen non bon (3 et 5 superflues, 6 manquante). Le français pèse lourd : sans ce critère, les n° 9 et 10 de Mistral comptent, soit 4/10 pour Mistral contre 6/10.
  - **Chaque modèle confirme ses propres questions** au second passage : les taux de 6/10 et 4/10 ne mesurent pas seulement la qualité des questions.
- **Risques pour la phase 4, non corrigés :**
  - **Le second passage laisse passer des erreurs et rejette de bonnes questions.** Mistral n° 6 demande « Qui sont les deux hôteliers » : le texte ne les nomme pas, et l'exemple passe. Mistral rejette ainsi ses bonnes questions n° 4 et 5.
  - **Les connecteurs ne sont pas fiables chez les deux modèles :** un connecteur rendu pour une seule justificative, MAIS ou EN_REVANCHE sans opposition dans le texte. À ne pas utiliser tels quels.
  - Qwen dépasse la limite de 4 justificatives et en donne parfois trop : le code rejette le premier cas, pas le second.
- **Écarts avec SPEC.md :** aucun. Le travail relève de §16 et prépare la phase 4, mais reste sur `phase-3` : la phase 3 n'est pas close et aucun exemple d'entraînement n'est produit. La décision de §16 est écrite ici, `SPEC.md` n'est pas modifié.
- **Tests :** `make test` : 343 passés, 1 ignoré, 1 désélectionné. `make test-complet` non requis (ni `grammar`, ni `verify`, ni `anonymize`, ni `ingest`, ni `worldgen`).
- **Suite prévue :** inchangée pour la phase 3 : `reports/phase-3.md` et les arbitrages de langue et de licence. En phase 4 : mesurer le second passage sur plus d'articles avant de lancer les 20 000 exemples.

## 2026-11-03 — Phase 3 (§16, préparation de la phase 4) — Enseignant : Qwen plus gros
- **Travail fait :** demande de Raphael : tester des Qwen plus gros que le 7B avant la génération de la phase 4. Téléchargés en Q4_K_M dans `D:/Nunda-donnees/modeles/enseignant/` : Qwen2.5-14B, Qwen2.5-32B, Qwen3-32B (dépôts officiels), Qwen3.5-27B et Qwen3.5-35B-A3B (`bartowski` : pas de GGUF officiel). SHA-256 contrôlés pour 14B, 3.5-27B et 3-32B. `ccm enseignant` prend maintenant la liste des modèles, `--n` et `--nom` ; le serveur démarre avec `--reasoning off` (Qwen3 et 3.5 réfléchissent sinon). 20 articles (graine 20261102 ; les 10 premiers sont ceux du 2026-11-02). Résultats : `D:/Nunda-donnees/enseignant/q-<modèle>.json`.
- **Mesures, 20 articles :**

  |  | Qwen2.5-7B | Qwen2.5-14B | Qwen3.5-27B |
  | --- | --- | --- | --- |
  | VRAM au pic, sur 24 576 Mio | 5 050 Mio | 10 104 Mio | 17 142 Mio |
  | Débit | 99 jetons/s | 58 jetons/s | 23 jetons/s |
  | Durée des 20 articles (3 appels chacun) | 20 s | 36 s | 78 s |
  | Gardées par les règles du §12 | 16/20 | 18/20 | 18/20 |
  | Lecture de l'agent : question bonne | 9/20 | 7/20 | 17/20 |
  | Parmi les gardées : bonnes | 8/16 | 6/18 | 15/18 |

  Qwen2.5-7B : sorties des 10 premiers articles identiques à celles du 2026-11-02 (`--reasoning off` sans effet sur lui). Même critère de lecture que le 2026-11-02 : réponse dans les justificatives, jeu juste (ni manquante ni superflue, titre de l'article ou intertitre « III. » compris), rien d'inventé, français correct.
  - **Qwen3.5-27B :** non bons n° 4 (4 missions sur 4 citées, la 4e manque : limite de 4 justificatives), 18 (titre superflu ; « est mise fin »), 20 (intertitre « III. » superflu). Rejetées à tort : n° 6 et 19, bonnes questions.
  - **Qwen2.5-14B :** pire que le 7B à la lecture. Il met souvent le titre de l'article [1] ou des propositions superflues, et fait des fautes d'accord (« Quels sont les étapes », « Quels sont les deux entités »).
- **Incident :** la première série (5 modèles en arrière-plan) a été arrêtée par Claude Code, mémoire du système basse, au chargement du 27B. Relancé seul au premier plan : la mémoire physique libre (hors cache) est descendue à 152 Mio. À suivre pour les modèles de plus de 18 Go.
- **Décisions :** aucune. **Recommandation de l'agent, non décidée :** Qwen3.5-27B comme enseignant. Prix : environ 4 fois plus lent que le 7B ; 20 000 exemples gardés à 90 % demandent environ 24 h de calcul contre environ 6 h, sans parallélisme. Le choix reste Qwen2.5-7B tant que Raphael n'a pas tranché.
- **Limites :** 20 articles ; lecture d'une seule personne, sans aveugle. Chaque modèle confirme ses propres questions au second passage. Qwen3-32B, Qwen2.5-32B et Qwen3.5-35B-A3B non testés (Raphael : « essaye seulement le 3.5 27B »). Le 27B vient d'une quantification communautaire.
- **Écarts avec SPEC.md :** aucun ; travail de §16, sur `phase-3`, aucun exemple d'entraînement produit.
- **Tests :** `make test` : 343 passés, 1 ignoré, 1 désélectionné.
- **Suite prévue :** choix de l'enseignant par Raphael (7B ou 3.5-27B), puis phase 4 comme prévu.

## 2026-11-03 — Phase 4 — Questions de l'enseignant sur Légifrance et Judilibre
- **Travail fait :** Raphael retient **Qwen3.5-27B** (Q4_K_M, `bartowski`) comme enseignant et demande la génération du §12 « Modèle enseignant ». Branche `phase-4` créée depuis `phase-3`. `uv run ccm questions` (`ccm/data/questions.py`) : un passage par article ou décision, Légifrance et Judilibre en alternance, même prompt et même second passage que la comparaison (« d'une décision de justice française » pour Judilibre). Sortie `D:/Nunda-donnees/enseignant/questions.jsonl`, une ligne par passage (source, pièce, `prop_id` de `droit.sqlite`, sortie de l'enseignant, réponses du second passage, motif de rejet) ; une relance reprend après la dernière ligne. Lancée à 22 h 50 dans un processus détaché (`Start-Process`), hors des commandes de Claude Code.
- **Passages :** Légifrance : articles de 3 à 8 phrases et de 400 à 1 800 caractères (54 012), comme la comparaison. Judilibre : dans chaque décision, une suite tirée au hasard de 3 à 8 PHRASE consécutives, 400 à 1 800 caractères, sans proposition qui contient maître, « Me », avocat, greffier, président, conseiller, magistrat, rapporteur ou procureur. Décisions sans telle suite : écartées. Ordre tiré avec la graine 20261103.
- **Réglage du serveur :** `--parallel 4`, contexte 4 096 par requête. Mesuré : 4,2 s par passage à 1 requête, 2,45 s à 4, 2,6 s à 8. Chargement sans mmap (`--load-mode none`) : 2 min 30 et 9,7 Go de RAM gardés ; mmap gardé.
- **Mesures provisoires, 2026-11-04 à 1 h 06** (3 823 passages) :

  |  | Passages | Gardés | Rejet total | « Réponse possible » sans les justificatives | « Pas de réponse » avec | Numéros invalides |
  | --- | --- | --- | --- | --- | --- | --- |
  | Légifrance | 1 912 | 1 703 | 10,9 % | 7,1 % | 3,6 % | 0,3 % |
  | Judilibre | 1 911 | 1 694 | 11,4 % | 4,6 % | 6,8 % | 0,1 % |
  | Total | 3 823 | 3 397 | 11,1 % | 5,8 % | 5,2 % | 0,2 % |

  Rythme : environ 1 600 exemples gardés par heure ; fin prévue vers 15 h le 2026-11-04.
- **Décisions :** moitié Légifrance, moitié Judilibre (10 000 chacun) : le §12 ne fixe pas la part. Exclusion des passages qui citent une personne : le moins de noms possible dans les questions (L111-13 COJ pour les magistrats ; noms d'avocats non occultés dans les décisions).
- **Écarts avec SPEC.md :** la phase 3 n'est pas close (`reports/phase-3.md` non écrit) : cette génération de phase 4 se fait sur demande de Raphael. `questions.jsonl` contient du texte de décisions et peut contenir des noms : fichier de travail, pas fichier d'entraînement ; la chaîne du §12 (noms, nombres, pointeurs) passera dessus.
- **Incident :** `tests/unit/test_questions.py` (questions du monde synthétique) écrasé par erreur au premier commit, restauré au suivant ; tests du générateur dans `tests/unit/test_questions_enseignant.py`.
- **Incident du 2026-11-04 :** à 3 h 15, Windows Update a redémarré le PC (KB5127936) et arrêté la génération. Dernière ligne écrite à 3 h 13 : 7 221 passages, 6 417 gardés, fichier intact. Relance à 4 h 18 : la reprise relisait chaque pièce déjà faite avant de la sauter, et `proposition.piece_id` n'a pas d'index (0,5 s par lecture), soit environ 1 h avant la première question. `passages()` prend maintenant `sauter` et omet ces pièces sans les lire ; ordre des passages inchangé. Relancé à 4 h 43, nouvelles lignes dès 4 h 46. Mises à jour non suspendues (choix de Raphael).
- **Bilan final, 2026-11-04 à 13 h 57 :** cible atteinte, 22 484 passages, **20 004 gardés**.

 | | Passages | Gardés | Rejet total | « Réponse possible » sans les justificatives | « Pas de réponse » avec | Numéros invalides |
 | --- | --- | --- | --- | --- | --- | --- |
 | Légifrance | 11 245 | 10 003 | 11,0 % | 6,9 % | 3,6 % | 0,5 % |
 | Judilibre | 11 239 | 10 001 | 11,0 % | 4,2 % | 6,6 % | 0,2 % |
 | Total | 22 484 | 20 004 | 11,0 % | 5,5 % | 5,1 % | 0,4 % |

 Les 4 exemples au-delà de 20 000 viennent des requêtes déjà parties quand le quota est atteint. Rythme après la relance : environ 1 475 gardés par heure.
- **Tests :** `make test` : 345 passés, 1 ignoré, 1 désélectionné.
- **Suite prévue :** chaîne du §12 (noms, nombres, pointeurs) sur `questions.jsonl` ; `reports/phase-3.md` toujours à écrire.

## 2026-11-04 — Phase 4 — Chargeur de données du réglage fin (§12, §13)
- **Travail fait :** demande de Raphael. `ccm/train/chargeur.py` et `ccm/data/negatives.py` (nom de l'arborescence du §3). Chaque exemple est construit à neuf à partir du stock de sa question, avec les fonctions de l'inférence :
  1. **Mélange pondéré :** `chargeur.poids` de `configs/finetune.yaml` (les parts du §12), renormalisés sur les sources présentes. Une époque est un plan fixé par la graine : parts par plus forts restes, questions de chaque source dans un ordre tiré pour l'époque, places mélangées.
  2. **Genre tiré :** abstention 12,5 % (justificatives et toutes leurs copies retirées du stock), conflit injecté 10 %, contrefactuel 5 %, sinon normal. Aucun genre pour une question sans réponse.
  3. **Contexte réel :** `chercher` (§7) sur le stock, avec un index BM25 en mémoire (`Index.en_memoire`). 80 % des exemples : les propositions manquantes que la cible cite sont ajoutées dans leur pièce, à leur place. 20 % : s'il en manque une, la cible devient ABSTENTION (genre `abstention_contexte`).
  4. **Indices tirés à chaque époque :** nouvelle `TableConversation`, avec une graine tirée de (graine, époque, place).
  5. **Masques :** `encode` avec le `Contexte` de l'automate. Un pas de référence hors de son masque est une erreur.
  - Sources : `SourceSynthetique` (stock de référence + `cible_de_reference`, lignes prises dans la copie gardée de leur groupe de doublons) et `SourcePublique` (`publics.stock_de`, factorisé hors de `convertir`, sans changement de comportement). `sources_disponibles` lit les parties d'entraînement avec les lecteurs de `ccm convertir` et les caches de zones.
  - Test du §13 : `tests/unit/test_chargeur.py`, 10 tests. Chaque pas de référence est dans son masque pour chaque genre et chaque source (synthétique, HotpotQA, PIAF, FinQA, SQuAD). Les tests couvrent aussi le mélange, les indices retirés et la structure gardée, l'abstention avec doublons, le conflit d'un autre rang trouvé par l'ingestion, le contrefactuel, le contexte incomplet et la règle 4.
- **Mesures :**
  - 3 dossiers synthétiques, parts relevées : 150 exemples en environ 7 s, aucun sauté.
  - Vraies sources publiques : 2 000 places, 1 985 exemples gardés, tous les pas dans leur masque. Durée 600 s, en un processus : environ 0,3 s par exemple. Une époque de 200 000 demande donc environ 17 h en un processus, ou environ 3 h sur 6 processus.
  - Replis : conflit 187 sur 187 ; contrefactuel 50 sur 93 ; 15 exemples sautés (Rejet).
  - Chargement des sources : 39 s.
- **Décisions (SPEC.md muet, option la plus simple) :**
  - **Les transformations se font sur le stock, pas sur l'exemple JSON.** Après chaque ajout, `dedoublonner` et `detecter_conflits` repassent sur le stock : l'arête CONFLIT d'un conflit injecté vient de l'ingestion. Si le conflit n'est pas trouvé (§5 : il faut une date au jour près, un nom commun et une heure ou des montants qui se recouvrent), l'exemple redevient normal et il est compté comme repli.
  - **Valeur changée :** seulement un nombre NUM. Mêmes positions et même nombre de chiffres ; le nombre doit être relu par l'extraction comme le même genre, à la même unité. Aucune date n'est changée : une date différente veut dire un autre fait (§5). « Inverser une règle » n'est pas fait.
  - **Contrefactuel :** la forme d'origine va dans une pièce `AUTRE`, de rang 0. Elle est retirée si l'ingestion la trouve en conflit avec la justificative, sinon la règle 4 imposerait un bloc CONFLIT.
  - **Règle 4 du §10 :** elle s'applique à toutes les sources. Un CITE en début de segment, dont la proposition a un conflit établi dans le contexte, devient un bloc CONFLIT avec ses partenaires non cités ailleurs.
  - **Parts et réglages :** conflit injecté 10 % (le §12 ne fixe pas la part ; c'est celle des conflits du corpus synthétique). 200 000 exemples par époque. Le stock synthétique passe aussi par `dedoublonner`.
  - **Mode citation seulement :** `encode` calcule les masques sans synthèse.
- **Écarts avec SPEC.md :** aucun sur les règles.
  - **Le conflit injecté ne prend pas sur les jeux publics** (0 sur 187). Il ne vient que du corpus synthétique, environ 1 sur 3 des essais sur 3 dossiers. À revoir avec Raphael : garder la règle du §5, ou viser d'autres phrases.
  - Le conflit supposé et le faux conflit (§12) ne sont pas faits : ils ne font pas partie de la tâche.
  - Il n'y a pas encore de source Légifrance et Judilibre : `questions.jsonl` n'est pas converti, et les 15 % sont répartis sur les autres sources.
  - L'abstention retire les justificatives et leurs doublons, comme le §12. Une autre ligne qui dit le même fait autrement peut rester, et la cible ABSTENTION serait alors fausse. C'est un risque.
- **Tests :** `make test` : 355 passés, 1 ignoré, 1 désélectionné. `make test-complet` non requis : `search`, `data` et `train` seulement ; ni `grammar`, ni `anonymize`, ni `ingest`, ni `worldgen` modifiés.
- **Suite prévue :** source Légifrance et Judilibre (chaîne du §12 sur `questions.jsonl`) ; parallélisme du chargeur ; `reports/phase-3.md` toujours à écrire.

## 2026-11-04 — Phase 4 — Chargeur : conflit injecté et abstention, choix de Raphael
- **Décisions de Raphael :**
  - **Conflit injecté :** la règle du §5 est gardée. L'arête CONFLIT vient toujours de l'ingestion, donc les conflits injectés viennent du corpus synthétique seulement.
  - **Abstention, option B :** pour le corpus synthétique, l'abstention se fonde sur la vérité terrain (« si ça aide l'entraînement à s'abstenir, c'est bien »).
- **Travail fait :** `Cas.temoins` (`ccm/train/chargeur.py`) = toutes les lignes des événements des justificatives (`Ligne.evenement` de `verite.json`). Cela couvre un autre témoin, une autre forme du nom et l'autre version d'un conflit.
  - **Abstention :** les justificatives, leurs témoins et leurs doublons sortent du stock. Si un témoin a été cité au tour précédent, le fait reste dans le contexte : l'exemple redevient normal (repli).
  - **Contexte incomplet (20 %) :** si une justificative manque mais qu'un témoin est dans le contexte, la réponse y est. Les manquantes sont alors ajoutées, au lieu de mettre ABSTENTION.
  - Jeux publics inchangés : ils n'ont pas de vérité terrain, et les justificatives et leurs doublons sont retirés comme avant.
  - Test ajouté : `test_abstention_synthetique_retire_tout_l_evenement`. Sur 10 questions, aucune justificative ni aucun témoin ne reste dans le contexte, et chaque pas est dans son masque.
- **Mesures :** sur 20 dossiers synthétiques, 418 des 713 questions avec réponse (59 %) ont au moins une autre ligne du même événement hors des lignes équivalentes de la question. Avec l'ancienne règle, leur ABSTENTION pouvait être fausse. 5 questions ont un témoin déjà cité.
- **Limite :** retirer tout l'événement retire aussi des lignes qui ne portent pas l'attribut demandé. Les abstentions sont donc un peu plus faciles, mais leur cible est sûre. 5 lignes d'étape sur 1 437 n'ont pas d'événement : pour elles, seules les lignes équivalentes sortent.
- **Écarts avec SPEC.md :** le §12 dit « retire les justificatives et leurs doublons ». Pour le synthétique, le code retire plus, sur décision de Raphael. `SPEC.md` n'est pas modifié.
- **Tests :** `make test` : 356 passés, 1 ignoré, 1 désélectionné.
- **Suite prévue :** inchangée (source Légifrance et Judilibre, parallélisme du chargeur, `reports/phase-3.md`).

## 2026-11-04 — Phase 4 — Choix du modèle de base et du GPU ; durée estimée de A0 et A1
- **Décisions de Raphael (§16) :** modèle de base de A : **SmolLM**. GPU : **une RTX 3090 (24 Go)**, rien d'autre. L'entraînement se fait par nuits de 8 h.
- **Mesure :** longueur des séquences A0 avec le tokenizer de SmolLM2-360M (`HuggingFaceTB/SmolLM2-360M`, tokenizer seul) sur 597 exemples du chargeur, toutes sources présentes (sans Légifrance ni Judilibre). T moyen 1 499, médiane 1 466, q90 2 503, max 3 546. Par source : synthétique 2 159, HotpotQA 1 314, FinQA 892, PIAF 601, SQuAD 175.
- **Estimation, à remplacer par la mesure de 20 minutes du §13 :**
  - SmolLM2-360M : 32 couches, dimension 960.
  - Environ 2,2 GFLOP par jeton à l'entraînement avec LoRA : environ 0,72 GFLOP en avant, multiplié par 3.
  - RTX 3090 : 71 TFLOPS en bf16 ; 15 à 35 % d'utilisation, soit environ 5 000 à 11 000 jetons/s.
  - Une époque = 200 000 × 1 500 = 3·10⁸ jetons, soit **7,5 à 17 h, environ 9 h**.
  - A0, 3 époques : 23 à 50 h, environ 28 h, soit **4 nuits (3 à 7)**.
  - A1, 2 époques depuis A0 : biais dense sans attention rapide, contexte de 2 500 jetons ; environ 1,5 fois plus lent. Environ 28 h, soit **4 nuits (3 à 6)**.
  - Chargeur : 0,3 s par exemple, soit 17 h de CPU par époque. Il faut 3 ou 4 processus de chargement pendant l'entraînement pour suivre le GPU.
- **Points ouverts :**
  - SmolLM2 n'a pas de taille entre 0,4 et 0,6 milliard (§9). Les tailles voisines sont 360 M, puis 1,7 milliard à la place de 1,5.
  - SmolLM2 est entraîné surtout sur de l'anglais, et nos données sont surtout en français.
  - SmolLM2-1.7B coûterait environ 5 fois plus : environ 140 h pour 3 époques. C'est au-delà des 5 jours du §15, cas 4.
  - Les résultats finaux demandent 3 graines (§13), ce qui triple les nuits des entraînements finaux.
- **Suite prévue :** inchangée ; mesure du débit réel au premier essai à blanc.

## 2026-11-04 — Phase 4 — Taille du modèle de base
- **Décision de Raphael :** A0 et A1 utilisent **SmolLM2-360M** seulement. Pas d'étape à 1,5 ou 1,7 milliard (« je n'ai pas 18 jours pour un réglage fin »).
- **Durée estimée :** environ 4 nuits de 8 h pour A0 et environ 4 nuits pour A1, à remplacer par la mesure du §13.
- **Écart avec SPEC.md :**
  - Le §9 prévoit 0,4 à 0,6 milliard, puis 1,5 milliard. 360 M est la taille de SmolLM2 la plus proche, et l'étape à 1,5 milliard est abandonnée.
  - Pour réduire la durée sans changer de modèle : baisser `exemples_par_epoque` (200 000 aujourd'hui), ou ne pas faire A1. Raphael n'a choisi ni l'un ni l'autre.

## 2026-11-05 — Phase 4 — Code de A0 (§9) et perte du §13
- **Travail fait :** demande de Raphael. `ccm/model/a0.py`, `ccm/train/a0.py`, `tests/unit/test_a0.py` ; dépendance `peft` ajoutée (§3).
  - **Tronc :** SmolLM2-360M (`AutoModel`, sans tête), LoRA rang 16, alpha 32, abandon 0,05 sur `q/k/v/o_proj` et `gate/up/down_proj` ; poids de base gelés.
  - **Jetons nouveaux :** table propre (`Vocabulaire` de A0, avec l'en-tête [REL] déjà écrit par `encode`) ; l'entrée passe par `inputs_embeds`. `num_attr` : 4 tables ajoutées au vecteur du slot.
  - **Deux passes :** l'entrée jusqu'avant [SORTIE] (cache gardé), puis la sortie. Vecteurs pointés : [/P] → linéaire → RMSNorm ; nombre et mention : état du slot. Après un pointeur : ⟨PT:X⟩ + `W_in` × vecteur pointé de la référence, gradient passant.
  - **Têtes :** `W_lex` sur les 25 + synthèse de `LEXIQUE_COMPLET` ; pointeurs P, N, M à 256 dimensions avec τ et b par famille ; sélection sigmoïde sur `r_p`. Masque de l'automate appliqué aux logits.
  - **Perte (§13) :** L_actions (pas de mention : −log de la somme des mentions autorisées du nom) + 0,5 · BCE de sélection, poids des positives = négatives / positives borné à 10.
  - Optimiseur : AdamW (0,9 ; 0,999), 2e-4 LoRA, 1e-3 modules nouveaux, décroissance 0,01, norme bornée à 1,0, bf16 (autocast) sur GPU.
- **Mesures :** surapprentissage voulu, 8 exemples synthétiques (dossier 0, chargeur, T 2 160 à 2 530), 200 pas d'un lot de 8 : perte 3,59 au pas 0, 1,20 au pas 10, 0,068 au pas 50, 1e-5 au pas 199. RTX 3090 : 705 s, environ 3,5 s par pas de 8 exemples, soit environ 5 400 jetons/s (bas de l'estimation du 2026-11-04 ; à remplacer par la mesure de 20 minutes).
- **Décisions (SPEC.md muet, option la plus simple) :** un contexte par passe avant (accumulation pour le lot) ; tronc en float32 avec autocast bf16 ; pas d'échauffement dans l'essai de surapprentissage ; ni décodage glouton ni sauvegarde de point de contrôle (pas dans la tâche).
- **Écarts avec SPEC.md :** aucun.
- **Tests :** `make test` : 359 passés, 1 ignoré, 1 désélectionné. 3 tests nouveaux sur un petit LLaMA tiré au hasard (CPU) : formes et gradients, pointeur de nom, surapprentissage.
- **Suite prévue :** décodage glouton sous masque, points de contrôle, essai à blanc du §13 (200 pas sur 1 000 exemples) et mesure du débit de 20 minutes.

## 2026-11-06 — Phase 4 — A0 : essai à blanc et mesure du débit (§13)
- **Travail fait :** `ccm/train/a0.py` : échauffement linéaire (500 pas), lot de 16 contextes par accumulation, points de contrôle (`sauver`, `recharger` : poids entraînés seulement, optimiseur, ordonnanceur, pas ; reprise au même exemple). `python -m ccm.train.a0 essai` : essai à blanc, rechargement dans un modèle neuf, puis 20 minutes de débit. Dossier `runs/2026-11-06-a0-essai/` : configs, commit, paquets, `metrics.jsonl`, `bilan.json`, `pas-200.pt`. Tests ajoutés : `test_point_de_controle` (reprise = même chemin, mêmes pertes), `test_perte_sans_proposition`.
- **Correction :** au premier essai, 9 pas sur 200 avaient une perte NaN. Ils contenaient un exemple d'abstention à contexte vide (P = 0), où la BCE de sélection est la moyenne d'un tenseur vide. Sans proposition, la perte de sélection vaut maintenant 0. Les poids n'étaient pas touchés, car aucun gradient n'était NaN. Ce premier essai est gardé dans `metrics-essai1-nan.jsonl`.
- **Mesures (RTX 3090, SmolLM2-360M + LoRA, bf16) :**
  - **Données :** 1 000 exemples réels de l'époque 0 (synthétique sur 20 dossiers rédigés en mémoire, HotpotQA, PIAF, FinQA, SQuAD). T moyen 1 504 jetons. Chargement 283 s, soit 0,28 s par exemple en un processus.
  - **Essai à blanc :** 200 pas × 16 contextes, 1 244 s. Perte moyenne 3,19 sur les 20 premiers pas, 1,67 sur les 20 derniers, aucun NaN. **La perte baisse.**
  - **Point de contrôle :** rechargé dans un modèle neuf. Écart des pertes sur 8 exemples : 0,0. Pas relu : 200.
  - **Débit (20 min, 193 pas) :** 2,57 contextes/s, 3 858 jetons/s, mémoire max 9,2 Go.
  - T1 : en A, l'écart est une mesure et non un test (§14). Il n'est pas mesuré ce soir.
- **Durée prévue de A0 :** 3 époques × 200 000 contextes ÷ 2,57/s = **65 h, soit 2,7 jours**. C'est sous les 3 jours visés et sous les 5 jours du §15. Cela fait environ 8 nuits de 8 h.
  - La mesure est plus lente que l'estimation du 2026-11-04 (28 h) : 3 858 jetons/s au lieu de 5 000 à 11 000.
  - Le chargeur demande 0,28 s de CPU par exemple, et le GPU en consomme un toutes les 0,39 s. Il faut au moins 1 processus de chargement en parallèle de l'entraînement, 2 pour avoir de la marge.
- **Décisions (SPEC.md muet, option la plus simple) :**
  - Après l'échauffement, le pas d'apprentissage reste constant : le §13 ne fixe pas de décroissance pour la phase 4.
  - La mesure du débit réutilise les 1 000 exemples de l'essai, pris en boucle, avec la même répartition des longueurs.
- **Écarts avec SPEC.md :** aucun.
- **Tests :** `make test` : 361 passés, 1 ignoré, 1 désélectionné.
- **Suite prévue :** chargeur en processus parallèles, rotation des points de contrôle tous les 2 000 pas (garder les 3 derniers et le meilleur), puis lancement de A0.
