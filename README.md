# carto

Données carroyées à 1 km (Insee, Filosofi 2021) et outil de test visuel pour l'étude de l'habitat périurbain. Secteur test : Loire-Atlantique (44).

- `scripts/build.py` : télécharge et prépare les données d'un département (exécuté par GitHub Actions).
- `data/` : extraits Insee du département (csv, parquet), toutes variables.
- `docs/` : l'appli web (GitHub Pages) et son fichier de données `docs/data/44.json`.
- `PLAN.md` : plan de travail et sources mobilisables.

Sources : Insee (Filosofi 2021, carreaux de 1 km), IGN (contours, BD TOPO pour l'eau), à défaut OpenStreetMap.
