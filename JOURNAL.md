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
