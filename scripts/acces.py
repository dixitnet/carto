#!/usr/bin/env python3
"""Éloignement aux services, agrégé au carreau de 1 km.

Source : Insee, « Localisation et accès de la population aux équipements » (BPE, distancier
Metric-OSRM), carreaux de 200 m, un fichier parquet par région sur data.gouv.fr.
Pour chaque usage défini dans scripts/usages.json, on retient l'équipement le plus proche parmi
les types regroupés, puis on calcule par carreau de 1 km la moyenne pondérée par la population
de la distance routière (km) et de la durée en voiture (minutes).

Sortie : data/acces_1km.parquet (x, y en EPSG:3035, pop, d_<usage>, t_<usage>).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://www.data.gouv.fr/api/1/datasets/67fe0fe2423db9c4a05d8ced/"
METRO = ["11", "24", "27", "28", "32", "44", "52", "53", "75", "76", "84", "93", "94"]
USAGES = json.loads((ROOT / "scripts" / "usages.json").read_text())
SORTIE = ROOT / "data" / "acces_1km.parquet"
TEMOIN = ROOT / "data" / "acces_1km.json"


def log(*a):
    print(*a, flush=True)


def main():
    config = {"usages": USAGES, "millesime": "2025"}
    if SORTIE.exists() and TEMOIN.exists() and json.loads(TEMOIN.read_text()).get("config") == config \
            and "--force" not in sys.argv:
        log("Accès aux équipements : déjà à jour, rien à faire.")
        return
    res = requests.get(API, timeout=60).json()["resources"]
    urls = {}
    for r in res:
        t = r.get("title", "")
        if t.startswith("donnees_2025_reg") and t.endswith(".parquet"):
            urls[t[len("donnees_2025_reg"):-len(".parquet")]] = r["url"]
    code2usage = {c: u for u, v in USAGES.items() for c in v["types"]}
    liste = ",".join(f"'{c}'" for c in code2usage)
    cas = "CASE typeeq_id " + " ".join(f"WHEN '{c}' THEN '{u}'" for c, u in code2usage.items()) + " END"
    morceaux = []
    tmp = Path("/tmp/acces.parquet")
    for reg in METRO:
        t0 = time.time()
        subprocess.run(["curl", "-sSL", "--retry", "5", "--retry-delay", "10", "-o", str(tmp), urls[reg]], check=True)
        con = duckdb.connect()
        df = con.execute(f"""
            SELECT X, Y, any_value(pop) AS pop, {cas} AS usage, min(distance) AS d, min(duree) AS t
            FROM read_parquet('{tmp}') WHERE typeeq_id IN ({liste}) GROUP BY X, Y, usage
        """).df()
        con.close()
        tmp.unlink()
        if reg == METRO[0]:
            log("  exemple de lignes :", df.head(3).to_dict("records"))
        if df["Y"].median() > 5e6:  # Lambert-93 : on reprojette vers la grille européenne
            from pyproj import Transformer
            tr = Transformer.from_crs(2154, 3035, always_xy=True)
            df["X"], df["Y"] = tr.transform(df["X"].to_numpy(), df["Y"].to_numpy())
            if reg == METRO[0]:
                log("  coordonnées en Lambert-93, reprojetées en EPSG:3035")
        df["x"] = (np.floor(df["X"] / 1000) * 1000).astype(int)
        df["y"] = (np.floor(df["Y"] / 1000) * 1000).astype(int)
        df["pd"], df["pt"] = df["pop"] * df["d"], df["pop"] * df["t"]
        g = df.groupby(["x", "y", "usage"], as_index=False)[["pop", "pd", "pt"]].sum()
        morceaux.append(g)
        log(f"  région {reg} : {len(df)} lignes à 200 m -> {len(g)} à 1 km, {time.time() - t0:.0f} s")
    g = pd.concat(morceaux).groupby(["x", "y", "usage"], as_index=False).sum()
    g["d"], g["t"] = (g["pd"] / g["pop"]).round(2), (g["pt"] / g["pop"]).round(1)
    large = g.pivot(index=["x", "y"], columns="usage", values=["d", "t"])
    large.columns = [f"{a}_{b}" for a, b in large.columns]
    pop = g.groupby(["x", "y"])["pop"].max().rename("pop_acces")
    large = large.join(pop).reset_index()
    large.to_parquet(SORTIE, index=False)
    TEMOIN.write_text(json.dumps({"config": config, "carreaux": int(len(large)),
                                  "source": "Insee, accès aux équipements 2025 (BPE, distancier Metric-OSRM)"},
                                 ensure_ascii=False, indent=1))
    log(f"Écrit {SORTIE} : {len(large)} carreaux de 1 km")
    log(large.describe().round(1).T.to_string())


if __name__ == "__main__":
    main()
