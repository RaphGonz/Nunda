# Licences des données et des modèles

Une ligne par jeu de données ou modèle téléchargé, vérifiée au téléchargement (SPEC.md §3, §15 cas 3).

| Ressource | Source | Licence | Usage prévu | Vérifiée le |
| --- | --- | --- | --- | --- |
| Wikidata : libellés et alias français des humains (Q5), correspondance exacte sur nos noms | query.wikidata.org (SPARQL), `ccm/data/worldgen/wikidata.py` | CC0 1.0 (données structurées de Wikidata) | Liste d'exclusion du générateur de monde (SPEC.md §12) : `ccm/data/worldgen/exclus_wikidata.txt` | 2026-10-15 |
| Tesseract 5.4.0 (exécutable, build UB Mannheim) | winget `UB-Mannheim.TesseractOCR` | Apache 2.0 | OCR de secours de l'ingestion (SPEC.md §5, étape 1), appelé en sous-processus, hors ligne | 2026-10-19 |
| Modèle Tesseract `fra.traineddata` (SHA-256 `eac01c1d…`) | github.com/tesseract-ocr/tessdata | Apache 2.0 | Même usage ; rangé dans `runs/modeles/tessdata/` (hors de git) | 2026-10-19 |
