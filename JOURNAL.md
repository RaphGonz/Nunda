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
  - §16 « Modèle enseignant » : **Qwen, 7B, local**. Mistral écarté par Raphael (restriction sur l'entraînement d'autres modèles). Qwen2.5-7B-Instruct est sous Apache 2.0 (fichier `LICENSE` du dépôt Hugging Face, lu le 2026-10-18) ; la version exacte s'écrira dans `DATA_LICENSES.md` au téléchargement.
  - COURRIER : motif d'en-tête à choisir sur de vrais dossiers ; pas de changement de §5 pour l'instant.
- **Écarts avec SPEC.md :** §3 et §5 nomment encore PyMuPDF (changement validé, à faire en phase 2).
- **Suite prévue :** phase 2 (SPEC.md §5, §6, §7) : branche `phase-2` ; d'abord SPEC.md §3 et §5 avec la bibliothèque d'ingestion sans copyleft (pdfplumber ou pypdfium2, à mesurer sur le niveau 0), puis extraction.
