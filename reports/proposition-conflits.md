# Proposition : conflits à deux niveaux

État : **proposition, à valider par Raphael**. SPEC.md n'est pas modifié.
Origine : séance du 2026-10-21 (JOURNAL.md). La règle de §5 donne une précision de 0,0003 sur
la validation ; la règle « même fait » mesurée ensuite donne 0,86.

## Principe
Il y a deux sortes de conflits, et chacune va là où elle est fiable.

| | Niveau 1 : conflit établi | Niveau 2 : conflit supposé |
| --- | --- | --- |
| Qui le trouve | Le code, à l'ingestion (arête CONFLIT) | Le modèle, à la réponse |
| Ce qu'il couvre | Même fait, valeur différente ; versions d'un même article | Tout le reste : reformulations, contradictions logiques, une règle qui implique le contraire d'une autre |
| Garantie | Oui : le vérificateur affiche l'autre version, quels que soient les poids | Non : affiché comme hypothèse, à vérifier par l'humain |
| Cible | Précision ≥ 0,9 (seuil de phase 2) | Mesurée, sans seuil au départ |

Le modèle ne peut toujours rien inventer : un conflit supposé ne fait que pointer des
propositions du contexte, affichées avec leur texte original.

## Changements proposés dans SPEC.md

### §5, « Détection des conflits » (remplace les étapes 1 à 4)
Deux propositions de pièces différentes sont en conflit établi dans deux cas.

**A. Même fait, valeur différente** (pièces de dossier).
1. **Même fait.** Elles ont une date au jour près en commun, un nom de famille en commun (§6 :
   mot tout en majuscules, sinon le dernier mot de la norme), un lieu en commun si les deux en
   ont un, et le même type d'acte (liste de mots par type dans `configs/ingest.yaml` :
   virement, signature, arrestation, appel, rencontre, vol, contrôle, constat…) si les deux en
   ont un.
2. **Valeur différente.** Heures du jour alignées par ordre, différentes ; ou montants en
   euros qui se recouvrent en partie (un montant commun, un autre différent). Les valeurs se
   comparent en décimal exact (« 45 104 € » = « 45 104,00 € »).
3. **Négation.** Même fait, et une marque de négation dans une seule des deux, cherchée hors
   des mentions de noms (« Hugo Non » n'est pas une négation).

Une date différente veut dire un autre fait, jamais un conflit. Un montant seul différent
non plus : un événement a souvent plusieurs montants, et chaque pièce peut en citer un autre.

**B. Versions d'un même article** (textes de rang LOI).
Deux propositions qui commencent par la même référence d'article (« Article L. 121-1 »,
norme REF égale) et dont les textes diffèrent. Avec l'arbre de Légifrance (étape 9) : aussi
une source qui cite un article dans une version qui n'est plus en vigueur.

**Limite écrite (remplace l'actuelle).** Le code ne trouve ni les reformulations ni les
contradictions logiques. Le modèle les signale au niveau 2. Le conflit sur une personne
(« c'est Martin » / « c'est Joly ») n'est pas au niveau 1 en v1 : les formes d'un même nom
(« L.M. », « Mme Rot ») le rendent trop peu sûr avant les relations de §6.

### §10, grammaire
Le lexique reste à 25 jetons : le conflit supposé réutilise `SANS_PREUVE`, comme `SAME`.

```text
CONFLIT(p, p′, …)          → CONFLIT P P+ FIN_CONFLIT                 (niveau 1)
CONFLIT_SUPPOSE(p, p′, …)  → CONFLIT SANS_PREUVE P P+ FIN_CONFLIT     (niveau 2)
```

| État | Pas autorisés |
| --- | --- |
| CONFLIT SANS_PREUVE, premier P | Toute proposition du contexte |
| CONFLIT SANS_PREUVE, P suivants | Une autre proposition du contexte, absente du bloc ; 4 P au plus |

Aucune impasse : le segment demande deux propositions dans le contexte.

### §10, ordre des suites de référence
Point 4 : « Un bloc CONFLIT à la place d'un CITE quand la proposition a un conflit établi dans
le contexte ; un bloc CONFLIT SANS_PREUVE quand l'exemple porte un conflit supposé. »

### §11, vérificateur et rendu
- Règle 4 (conflits) : inchangée ; elle ne lit que les arêtes (niveau 1). Un conflit supposé
  n'entraîne aucun ajout forcé.
- Nouveau gabarit :

| Pas | Texte affiché |
| --- | --- |
| CONFLIT SANS_PREUVE | « Contradiction possible entre ces passages (lecture du modèle, à vérifier). » puis chaque source avec son extrait ; puis « Rang : … » si les rangs sont connus et différents |

Le test de propriété de §11 reste vrai : le gabarit est fixe, les extraits sont des textes
originaux du contexte.

### §12, données d'entraînement
- Type « Conflit » (10 %) : moitié bloc CONFLIT (arête), moitié bloc CONFLIT SANS_PREUVE.
- Sources de conflits supposés :
  - corpus synthétique : les versions contradictoires que le code ne trouve pas (le second
    témoin parle avec un autre gabarit) ; c'est le cas de 98 paires sur 137 en validation ;
  - textes juridiques : versions successives d'un article ; paires règle / exception
    contradictoires ; questions de l'enseignant (phase 4).
- Exemples négatifs (autant que de positifs) : deux passages compatibles (règle générale et
  règle spéciale, même fait et mêmes valeurs dit deux fois, deux actes différents le même
  jour). La cible n'a pas de bloc conflit.

### §14, mesures
| Mesure | Définition |
| --- | --- |
| Conflit établi | Précision et rappel de la détection à l'ingestion (A et B séparément) ; taux d'affichage (100 % par construction) |
| Conflit supposé | Précision jugée par un humain sur 200 réponses ; rappel sur les conflits injectés et sur les versions contradictoires non trouvées par le code ; taux de conflits supposés sur les exemples négatifs |

### §2, seuil de la phase 2
Ajouter : « précision des conflits établis ≥ 0,9 sur le niveau 0 (réglage sur la validation,
mesure finale une seule fois sur le test) ».

### §16
« Conflits reformulés » : tranché, action « conflit supposé » du modèle (niveau 2).

## Questions pour Raphael
1. Valides-tu les deux niveaux et la forme `CONFLIT SANS_PREUVE` (lexique inchangé) plutôt
   qu'un 26e jeton ?
2. Rappel minimal du niveau 1 en phase 2 ? Proposition : ≥ 0,5 sur les conflits d'heure et de
   montant (meilleure mesure du soir : 63 / 81).
3. Liste des types d'acte : elle est réglée sur le vocabulaire des gabarits ; sur de vraies
   pièces, il faudra la reprendre. D'accord pour la garder dans `configs/ingest.yaml` comme
   valeur de départ ?
4. Versions d'articles (B) : à faire dès la phase 2 sur la référence en tête de proposition,
   ou attendre l'arbre de Légifrance (étape 9, phase 7) ?

## Mesures de départ (validation, mentions de référence, 137 paires de référence)
| Règle | Vrais | Faux | Précision |
| --- | --- | --- | --- |
| §5 actuelle | 2 | 5 807 | 0,0003 |
| Même fait, heure, lieu compatible | 59 | 10 | 0,86 |
| Même fait, montants en recouvrement partiel (décimal exact) | 4 | 0 | 1,00 |
| Les deux, et la négation hors des noms | 63 | 10 | 0,86 |

Le type d'acte n'est pas encore mesuré. Les 10 faux positifs restants sont deux actes
différents d'une même personne le même jour (« signe un accord à 5 h 17 » / « est arrêtée à
9 h 35 ») : c'est ce que le type d'acte doit retirer.
