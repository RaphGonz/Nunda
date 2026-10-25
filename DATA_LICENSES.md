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
