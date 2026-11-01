# Licences des données et des modèles

Une ligne par jeu de données ou modèle téléchargé, vérifiée au téléchargement (SPEC.md §3, §15 cas 3).

| Ressource | Source | Licence | Usage prévu | Vérifiée le |
| --- | --- | --- | --- | --- |
| Wikidata : libellés et alias français des humains (Q5), correspondance exacte sur nos noms | query.wikidata.org (SPARQL), `ccm/data/worldgen/wikidata.py` | CC0 1.0 (données structurées de Wikidata) | Liste d'exclusion du générateur de monde (SPEC.md §12) : `ccm/data/worldgen/exclus_wikidata.txt` | 2026-10-15 |
| Tesseract 5.4.0 (exécutable, build UB Mannheim) | winget `UB-Mannheim.TesseractOCR` | Apache 2.0 | OCR de secours de l'ingestion (SPEC.md §5, étape 1), appelé en sous-processus, hors ligne | 2026-10-19 |
| Modèle Tesseract `fra.traineddata` (SHA-256 `eac01c1d…`) | github.com/tesseract-ocr/tessdata | Apache 2.0 | Même usage ; rangé dans `runs/modeles/tessdata/` (hors de git) | 2026-10-19 |
| GLiNER `urchade/gliner_multi-v2.1` (révision `443d26d6`, poids SHA-256 `2100142f…`) ; entraîné sur `urchade/pile-mistral-v0.1` (Apache 2.0) | huggingface.co, `ccm modeles` | Apache 2.0 | Détecteur D1 de l'étape 5 (SPEC.md §6), encodeur non génératif, lu hors ligne dans `runs/modeles/` | 2026-10-22 |
| mDeBERTa-v3-base `microsoft/mdeberta-v3-base` (révision `a0484667`), configuration et tokenizer | huggingface.co, `ccm modeles` | MIT | Encodeur de GLiNER (D1) | 2026-10-22 |
| spaCy `fr_core_news_lg` 3.8.0 | github.com/explosion/spacy-models (dépendance figée dans `uv.lock`) | LGPL-LR (Lesser General Public License for Linguistic Resources) | Détecteur D2 de l'étape 5, appelé tel quel, non modifié, non redistribué. La LGPL-LR n'impose rien à l'usage ; ses obligations portent sur la redistribution de la ressource | 2026-10-22 |
| Dictionnaire Hunspell français Dicollecte 7.7 (`fr.dic`, `fr.aff`) | github.com/LibreOffice/dictionaries (commit `67032ee9`), `ccm modeles` | MPL 2.0 | Lexique des mots courants du détecteur D4 (SPEC.md §6), lu par `spylls` (MPL 2.0) | 2026-10-22 |
| Dictionnaire Hunspell `en_US` (SCOWL, 2020.12.07) | github.com/LibreOffice/dictionaries (commit `67032ee9`), `ccm modeles` | Licence SCOWL (permissive, avec avis de copyright ; parties BSD, WordNet) | Même usage (formes courantes de l'anglais) | 2026-10-22 |
| HotpotQA, réglage « distracteurs » (`train` 90 447 questions, `validation` 7 405) | huggingface.co `hotpotqa/hotpot_qa`, révision `1908d6af` (Parquet), `ccm jeux` ; l'hôte d'origine `curtis.ml.cmu.edu` ne résout plus | CC BY-SA 4.0 (site hotpotqa.github.io, carte du dépôt). Attribution et partage à l'identique : **à signaler pour des poids ouverts** | Réglage fin, chaînes de citations (SPEC.md §12) | 2026-10-31 |
| SQuAD 2.0 (`train-v2.0`, `dev-v2.0`) | rajpurkar.github.io/SQuAD-explorer, `ccm jeux` | CC BY-SA 4.0 (page du jeu). Attribution et partage à l'identique : **même remarque** | Réglage fin, questions sans réponse → ABSTENTION | 2026-10-31 |
| FinQA (`train`, `dev`, `test`) | github.com/czyssrs/FinQA (branche `main`, SHA-256 figés dans `ccm/data/jeux.py`), `ccm jeux` | MIT (`LICENSE`, Zhiyu Chen, 2021 ; couvre le dépôt, dont `dataset/`) | Réglage fin, CALCUL sur nombres cités | 2026-10-31 |
| TAB, Text Anonymization Benchmark (`echr_train`, `echr_dev`, `echr_test`) | github.com/NorskRegnesentral/text-anonymization-benchmark (branche `master`), `ccm jeux` | MIT (`LICENSE.txt` et README : « TAB is released under an MIT License », Norsk Regnesentral). **Contient de vrais noms** (arrêts publics de la CEDH) | Évaluation seulement : rappel de la détection ; jamais d'entraînement | 2026-10-31 |
| PIAF v1.2 | data.gouv.fr (Etalab), `ccm jeux` | **CC BY-SA, retenue par Raphael le 2026-10-31.** Sources contradictoires : data.gouv « License Not Specified » ; Hugging Face étiquette MIT, section licence vide ; article LREC 2020 (note 6) « CC-BY-SA », seule déclaration des auteurs. Attribution et partage à l'identique | Réglage fin, citation en français | 2026-10-31 |
| FQuAD : **NON TÉLÉCHARGÉ, accès non obtenu** | huggingface.co `illuin/fquad` (HTTP 401) ; `fquad.illuin.tech` ne résout pas | **Non lue** : page inaccessible. Non commerciale d'après SPEC.md §12, à vérifier | Réglage fin, citation en français : en attente d'un accès | 2026-10-31 |
| LEGI, stock global `Freemium_legi_global_20250713-140000.tar.gz` (dernier stock publié ; SHA-256 `f862b4a2…`) | echanges.dila.gouv.fr/OPENDATA/LEGI, `ccm jeux`, `ccm legi` | Licence Ouverte 2.0 (fiche `DILA_LEGI_Presentation_20170824.pdf`, lue). À mentionner : paternité DILA, URL de téléchargement, nom et date du fichier. Avertissement DILA sur les données personnelles lu : pas de réidentification | Texte juridique (SPEC.md §12) ; seuls les articles en vigueur des codes sont gardés | 2026-11-01 |
| Judilibre, échantillon de 50 000 décisions au plus | API PISTE `/scan`, `ccm judilibre` | Licence Ouverte 2.0, CGU open data V8 de la Cour de cassation et CGU de PISTE (lues). Ne pas altérer ni dénaturer ; juridiction, formation, siège et date attachés à chaque décision ; citer la source et la date de mise à jour ; tenir à jour ; aucun profilage des magistrats et greffiers (L111-13 COJ) ; quotas à ne pas contourner ; clé à ne pas divulguer. **Contient des données personnelles résiduelles** | Texte juridique (SPEC.md §12) | 2026-11-01 |

## Poids fermés et usage commercial (Raphael, 2026-10-31)

Synthèse de recherche, pas un avis juridique : à faire valider par un juriste avant toute vente. Détail dans `JOURNAL.md`.

- **CC BY-SA (HotpotQA, SQuAD, PIAF, Wikipédia) :** à exclure du modèle commercial, sauf avis contraire d'un juriste. Une traduction reste soumise à la même licence.
- **MIT (FinQA, TAB) :** compatible, avec l'avis de copyright.
- **FQuAD :** à exclure (non commerciale d'après SPEC.md §12, non vérifié).
- **Légifrance, Judilibre, non téléchargés :** Licence Ouverte 2.0 et conditions d'utilisation à accepter ; voir les réserves du journal pour Judilibre.
