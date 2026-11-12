#!/usr/bin/env python3
"""Prépare les données carroyées à 1 km d'un département pour l'appli carto.

Sources :
  - Insee, Filosofi 2021, carreaux de 1 km (csv)
  - Contours des départements (france-geojson, d'après IGN Admin Express)
  - Surfaces en eau : IGN BD TOPO (WFS Géoplateforme), à défaut OpenStreetMap (Overpass)

Sorties :
  - data/filosofi2021_1km_<dept>.csv et .parquet : toutes les variables Insee du département
  - docs/data/<dept>.json : fichier compact lu par l'appli (carreaux habités + fond de plan)

Usage : python scripts/build.py --dept 44
        (options de test : --filosofi fichier.csv --deps fichier.geojson --no-hydro)
"""
import argparse
import io
import json
import math
import re
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "dixitnet-carto/1.0 (+https://github.com/dixitnet/carto)"}
FILOSOFI_URL = "https://www.insee.fr/fr/statistiques/fichier/8735171/Filosofi2021_carreaux_1km_csv.zip"
DEPS_URL = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements.geojson"
WFS_URL = "https://data.geopf.fr/wfs/ows"
WFS_LAYERS = ["BDTOPO_V3:surface_hydrographique"]
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
CELL = 1000  # mètres
MARGE = 4  # carreaux de marge autour du département
LOG_COLS = ["log_av45", "log_45_70", "log_70_90", "log_ap90", "log_inc"]


def log(*a):
    print(*a, flush=True)


def get(url, **kw):
    for essai in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 180), **kw)
            if r.status_code == 200:
                return r
            log(f"  HTTP {r.status_code} sur {url[:90]}")
        except requests.RequestException as e:
            log(f"  erreur réseau : {e}")
        time.sleep(5 * (essai + 1))
    raise RuntimeError(f"Téléchargement impossible : {url}")


# ---------------------------------------------------------------- Filosofi
def extraire_csv(blob, nom="archive"):
    """Renvoie [(nom, bytes)] des csv trouvés, en ouvrant zip et 7z imbriqués."""
    trouves = []
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for n in z.namelist():
                if n.endswith("/"):
                    continue
                trouves += extraire_csv(z.read(n), n)
    elif blob[:6] == b"7z\xbc\xaf\x27\x1c":
        import py7zr, tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with py7zr.SevenZipFile(io.BytesIO(blob)) as z:
                z.extractall(tmp)
            for p in Path(tmp).rglob("*"):
                if p.is_file():
                    trouves += extraire_csv(p.read_bytes(), p.name)
    elif nom.lower().endswith(".csv"):
        trouves.append((nom, blob))
    return trouves


def lire_filosofi(chemin_local=None):
    if chemin_local:
        fichiers = [(Path(chemin_local).name, Path(chemin_local).read_bytes())]
    else:
        log("Téléchargement Filosofi 2021 (1 km)…")
        fichiers = extraire_csv(get(FILOSOFI_URL).content)
    log("  fichiers csv :", [n for n, _ in fichiers])
    cadres = []
    for nom, blob in fichiers:
        entete = blob[:2000].decode("utf-8", "replace").splitlines()[0]
        sep = ";" if entete.count(";") > entete.count(",") else ","
        df = pd.read_csv(io.BytesIO(blob), sep=sep, dtype=str)
        df.columns = [c.strip().lower() for c in df.columns]
        idcol = next((c for c in df.columns if c.startswith("id") and "1km" in c), None) or next(
            c for c in df.columns if df[c].astype(str).str.contains("CRS3035RES1000m", regex=False).any()
        )
        df = df.rename(columns={idcol: "idcar_1km"})
        log(f"  {nom} : {len(df)} lignes, séparateur « {sep} », {len(df.columns)} colonnes")
        cadres.append(df)
    df = pd.concat(cadres, ignore_index=True)
    return df[df["idcar_1km"].str.contains("CRS3035RES1000m", regex=False)].copy()


def filtrer_dept(df, dept):
    geo = next(c for c in df.columns if "cog" in c or "depcom" in c)
    codes = df[geo].fillna("").str.replace(r"[^0-9A-Za-z]", "", regex=True)
    # codes commune de 5 caractères, concaténés ; on garde le carreau si l'un d'eux est dans le département
    motif = re.compile(rf"^(?:.{{5}})*{re.escape(dept)}.{{{5 - len(dept)}}}")
    garde = codes.apply(lambda s: bool(motif.match(s)))
    out = df[garde].copy()
    out["dept_principal"] = codes[garde].str[: len(dept)].eq(dept).astype(int)
    m = out["idcar_1km"].str.extract(r"N(\d+)E(\d+)")
    out["y"] = m[0].astype(int)
    out["x"] = m[1].astype(int)
    num = [c for c in out.columns if c not in ("idcar_1km", geo)]
    for c in num:
        out[c] = pd.to_numeric(out[c].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return out, geo


# ---------------------------------------------------------------- fond de plan
def charger_deps(chemin_local=None):
    if chemin_local:
        gj = json.loads(Path(chemin_local).read_text())
    else:
        log("Téléchargement des contours départementaux…")
        gj = get(DEPS_URL).json()
    g = gpd.GeoDataFrame.from_features(gj["features"], crs=4326).to_crs(3035)
    g["geometry"] = g.geometry.buffer(0)
    return g


def hydro_wfs(bbox3035):
    """Surfaces en eau IGN BD TOPO dans l'emprise (EPSG:3035)."""
    emprise = gpd.GeoSeries([box(*bbox3035)], crs=3035).to_crs(2154).total_bounds
    for couche in WFS_LAYERS:
        geoms, debut = [], 0
        try:
            while True:
                params = {
                    "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                    "TYPENAMES": couche, "SRSNAME": "EPSG:2154",
                    "BBOX": ",".join(f"{v:.0f}" for v in emprise) + ",EPSG:2154",
                    "OUTPUTFORMAT": "application/json", "COUNT": 5000, "STARTINDEX": debut,
                }
                feats = get(WFS_URL, params=params, timeout=300).json().get("features", [])
                for f in feats:
                    if f.get("geometry"):
                        geoms.append(shape(f["geometry"]))
                log(f"  WFS {couche} : +{len(feats)} objets (total {len(geoms)})")
                if len(feats) < 5000 or debut > 400000:
                    break
                debut += 5000
            if geoms:
                g = gpd.GeoSeries(geoms, crs=2154).to_crs(3035)
                return g, f"IGN BD TOPO ({couche})"
        except Exception as e:  # noqa: BLE001
            log(f"  WFS {couche} en échec : {e}")
    return None, None


def hydro_overpass(bbox3035):
    from shapely.ops import polygonize

    w, s, e, n = gpd.GeoSeries([box(*bbox3035)], crs=3035).to_crs(4326).total_bounds
    q = (
        f"[out:json][timeout:240];(way[natural=water]({s},{w},{n},{e});"
        f"relation[natural=water]({s},{w},{n},{e}););out geom;"
    )
    for url in OVERPASS_URLS:
        try:
            r = requests.post(url, data={"data": q}, headers=UA, timeout=300)
            if r.status_code != 200:
                log(f"  Overpass HTTP {r.status_code}")
                continue
            lignes = []
            for el in r.json().get("elements", []):
                if el["type"] == "way" and "geometry" in el:
                    lignes.append([(p["lon"], p["lat"]) for p in el["geometry"]])
                elif el["type"] == "relation":
                    for m in el.get("members", []):
                        if m.get("role") != "inner" and "geometry" in m:
                            lignes.append([(p["lon"], p["lat"]) for p in m["geometry"]])
            from shapely.geometry import LineString

            polys = list(polygonize(unary_union([LineString(l) for l in lignes if len(l) > 1])))
            log(f"  Overpass : {len(polys)} surfaces en eau")
            if polys:
                return gpd.GeoSeries(polys, crs=4326).to_crs(3035), "OpenStreetMap (Overpass)"
        except Exception as e:  # noqa: BLE001
            log(f"  Overpass en échec : {e}")
    return None, None


def fond_de_plan(cells, deps, dept, avec_hydro=True):
    x0 = int(cells["x"].min()) - MARGE * CELL
    y0 = int(cells["y"].min()) - MARGE * CELL
    nx = (int(cells["x"].max()) - x0) // CELL + 1 + MARGE
    ny = (int(cells["y"].max()) - y0) // CELL + 1 + MARGE
    bbox = (x0, y0, x0 + nx * CELL, y0 + ny * CELL)
    log(f"Grille de fond : {nx} x {ny} carreaux")

    proches = deps[deps.intersects(box(*bbox))]
    terre = unary_union(list(proches.geometry)).intersection(box(*bbox))
    dep = unary_union(list(proches[proches["code"] == dept].geometry))

    carreaux = [box(x0 + i * CELL, y0 + j * CELL, x0 + (i + 1) * CELL, y0 + (j + 1) * CELL)
                for j in range(ny) for i in range(nx)]
    arbre = STRtree(carreaux)
    aire = float(CELL * CELL)

    part_terre = np.zeros(nx * ny)
    for k in arbre.query(terre, predicate="intersects"):
        part_terre[k] = carreaux[k].intersection(terre).area / aire
    dans_dept = np.zeros(nx * ny, dtype=int)
    for k in arbre.query(dep, predicate="intersects"):
        if carreaux[k].intersection(dep).area / aire >= 0.5:
            dans_dept[k] = 1

    eau_int = np.zeros(nx * ny)
    source_eau = "aucune (mer seulement)"
    if avec_hydro:
        g, src = hydro_wfs(bbox)
        if g is None:
            g, src = hydro_overpass(bbox)
        if g is not None:
            source_eau = src
            g = g[g.is_valid | g.buffer(0).is_valid].buffer(0)
            g = g[g.area >= 20000]  # on ignore les surfaces de moins de 2 ha
            log(f"  {len(g)} surfaces en eau de 2 ha ou plus")
            for geom in g:
                for k in arbre.query(geom, predicate="intersects"):
                    eau_int[k] += carreaux[k].intersection(geom).area / aire
    eau = np.clip((1 - part_terre) + np.minimum(eau_int, part_terre), 0, 1)
    niveaux = np.rint(eau * 9).astype(int)
    return {
        "x0": x0, "y0": y0, "nx": nx, "ny": ny,
        "eau": "".join(str(v) for v in niveaux),
        "dept": "".join(str(v) for v in dans_dept),
        "source_eau": source_eau,
    }


# ---------------------------------------------------------------- sortie
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dept", default="44")
    ap.add_argument("--filosofi")
    ap.add_argument("--deps")
    ap.add_argument("--no-hydro", action="store_true")
    a = ap.parse_args()

    df = lire_filosofi(a.filosofi)
    cells, geo = filtrer_dept(df, a.dept)
    if cells.empty:
        sys.exit(f"Aucun carreau trouvé pour le département {a.dept}")
    presents = [c for c in LOG_COLS if c in cells.columns]
    cells["logements"] = cells[presents].sum(axis=1) if presents else cells["men"]
    log(f"Département {a.dept} : {len(cells)} carreaux habités, "
        f"{cells['logements'].sum():.0f} logements, {cells['men'].sum():.0f} ménages, {cells['ind'].sum():.0f} individus")

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "docs" / "data").mkdir(parents=True, exist_ok=True)
    base = ROOT / "data" / f"filosofi2021_1km_{a.dept}"
    cells.to_csv(f"{base}.csv", index=False)
    cells.to_parquet(f"{base}.parquet", index=False)

    fond = fond_de_plan(cells, charger_deps(a.deps), a.dept, not a.no_hydro)

    exclus = {"idcar_1km", geo, "x", "y"}
    cols = [c for c in cells.columns if c not in exclus]
    lignes = []
    for r in cells.itertuples(index=False):
        d = r._asdict()
        ligne = [(d["x"] - fond["x0"]) // CELL, (d["y"] - fond["y0"]) // CELL]
        for c in cols:
            v = d[c]
            ligne.append(None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 1))
        lignes.append(ligne)
    sortie = {
        "meta": {
            "dept": a.dept, "maille_m": CELL, "crs": "EPSG:3035",
            "source": "Insee, Filosofi 2021, carreaux de 1 km",
            "source_eau": fond.pop("source_eau"),
            "genere_le": date.today().isoformat(),
            "definition_logements": "somme des logements par époque de construction (" + ", ".join(presents) + ")"
            if presents else "nombre de ménages fiscaux",
        },
        "fond": fond,
        "colonnes": ["ix", "iy"] + cols,
        "carreaux": lignes,
    }
    cible = ROOT / "docs" / "data" / f"{a.dept}.json"
    cible.write_text(json.dumps(sortie, separators=(",", ":")))
    log(f"Écrit {cible} ({cible.stat().st_size / 1e6:.2f} Mo), eau : {sortie['meta']['source_eau']}")


if __name__ == "__main__":
    main()
