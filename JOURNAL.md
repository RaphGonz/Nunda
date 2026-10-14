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
- **Travail fait :** relecture des écarts de `reports/phase-0.md` avec Raphael. `MarqueNombre` : `signe` obligatoire pour NUM, `precision` pour DATE (chacun interdit pour l'autre genre). `Exemple` : indices de `relations_props` contrôlés. Exemple de SPEC.md §4 et `tests/golden/exemple_spec.json` modifiés avec l'accord de Raphael (`"precision": "JOUR"`, `"relations_props": []`). 6 cas de test ajoutés. Rapport mis à jour ; étiquette `phase-0-ok`, fusion dans `main`.
- **Mesures :** `make test` : 35 tests passés ; clone neuf `make setup && make test` OK ; CI verte Ubuntu et Windows (`7f04c66`).
- **Décisions (Raphael) :** écart 1 → champs obligatoires par genre ; écart 2 → contrôle des indices, relation retirée de l'exemple ; écart 3 → sens par l'ordre du triplet, validé. Décision de l'agent : le champ de l'autre genre est interdit (un signe de date n'a pas de sens).
- **Écarts avec SPEC.md :** aucun ouvert. §16 : heures et dépense maximale RTX 3090, modèle enseignant 7B exact, toujours à fixer.
- **Suite prévue :** phase 1 (SPEC.md §12, corpus synthétique niveau 0) : générateur de monde, gabarits, contrôle des faits, graine fixe.
