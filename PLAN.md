# Habitat périurbain : plan de travail et sources

Secteur test : Loire-Atlantique (44), carreaux de 1 km (100 ha), grille européenne Inspire (EPSG:3035).
Clé de jointure commune à toutes les sources carroyées : l'identifiant Inspire du carreau.

## Étape 1 – Identifier les carreaux habités (en cours)

Objectif : fixer un seuil de densité de logements qui écarte l'habitat diffus, puis un plafond qui écarte l'urbain dense.

| Source | Apport | Maille | Accès |
|---|---|---|---|
| Insee, Filosofi 2021 | logements des ménages fiscaux (résidences principales), ménages, individus | 1 km et 200 m | ouvert, intégré |
| Cerema, Fichiers fonciers (tables carroyées) | tous les logements, y compris résidences secondaires et vacants | 100 m, 1 km, 10 km | ayants droit, à demander |
| IGN, BD TOPO (bâtiments) | emprises, usage, nombre de logements par bâtiment | bâtiment, à agréger | ouvert |

Points d'attention :
- 1 logement/ha = 100 logements par carreau de 1 km.
- Dans le 44, près d'un carreau habité sur deux est imputé par l'Insee (moins de 11 ménages) : en dessous de 0,1 logement/ha environ, les valeurs sont des approximations.
- Filosofi ignore résidences secondaires et logements vacants, ce qui sous-estime le littoral.
- À tester ensuite : la maille de 200 m, plus pertinente pour séparer bourgs, lotissements et diffus au sein d'un même carreau de 1 km.

## Étape 2 – Caractériser les logements

| Source | Variables | Maille |
|---|---|---|
| Insee, Filosofi 2021 (déjà chargé) | maison / appartement, époque de construction (avant 1945, 1945-69, 1970-89, 1990 et après), surface totale, propriétaires, logements sociaux | 1 km |
| Cerema, Fichiers fonciers | année de construction précise, surface, nombre de pièces, taille de parcelle, type de propriétaire | parcelle, carroyé |
| CSTB, BDNB | DPE, matériaux, hauteur, époque | bâtiment |
| DGFiP, DVF | prix et volumes des transactions | parcelle |
| SDES, Sitadel | permis de construire, logements commencés | commune (géolocalisé partiel) |
| Cerema, consommation d'espaces NAF | flux annuels de consommation 2011-2025 | 1 km |

## Étape 3 – Accès aux services et à l'emploi

| Source | Variables | Maille |
|---|---|---|
| Insee, accès aux équipements (BPE + distancier Metric-OSRM) | distance et temps en voiture à l'équipement le plus proche, par type | 200 m, à agréger à 1 km |
| Insee, BPE 2025 géolocalisée | 235 types d'équipements en coordonnées | point |
| Insee, flux domicile-travail (RP 2023) | navettes commune à commune | commune |
| Insee, zonage en aires d'attraction des villes 2020 | pôle, couronne, hors attraction | commune |
| Insee, grille de densité 2025 (7 niveaux) | ceintures urbaines, bourgs ruraux, rural dispersé | commune |
| Insee, Sirene géolocalisé | établissements et tranches d'effectifs (approche de l'emploi au lieu de travail) | point |
| IGN, Géoplateforme (itinéraires, isochrones) | temps de trajet vers les pôles d'emploi | calcul à la demande |
| Transports : GTFS (transport.data.gouv.fr) | arrêts et fréquences des transports collectifs | point |

Limite : aucune donnée d'emploi ni de navettes n'existe au carreau. L'emploi est à reconstruire (Sirene) et les navettes restent communales.

## Étape 4 – Caractériser la population

| Source | Variables | Maille |
|---|---|---|
| Insee, Filosofi 2021 (déjà chargé) | âges (11 tranches), ménages d'une personne, de 5 personnes ou plus, familles monoparentales, ménages pauvres, niveau de vie | 1 km |
| Insee, RP 2023 carroyé | population par sexe, grands âges, lieu de naissance, résidence antérieure (mobilité résidentielle) | 1 km, métropole |
| Insee, RP à l'Iris | CSP, diplômes, activité, motorisation des ménages | Iris / commune |

## Étape 5 – Typologie et extension

- Croiser les quatre familles d'indicateurs pour dégager des types d'habitat périurbain.
- Confronter aux zonages officiels (couronnes des aires d'attraction, ceintures urbaines, rural sous influence).
- Étendre à la France entière : relancer `scripts/build.py --dept <code>` par département, ou adapter le script à l'ensemble des carreaux (environ 375 000 à 1 km).

## Outils

- `scripts/build.py` : téléchargement et préparation, exécuté par GitHub Actions (onglet Actions, « Préparer les données »).
- `data/` : extraits Insee complets du département (csv, parquet).
- `docs/` : appli web de test visuel (GitHub Pages).
