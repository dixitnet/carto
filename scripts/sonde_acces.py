#!/usr/bin/env python3
"""Sonde : décrit le jeu Insee « Localisation et accès de la population aux équipements » (data.gouv.fr)."""
import duckdb
import requests

API = "https://www.data.gouv.fr/api/1/datasets/67fe0fe2423db9c4a05d8ced/"
d = requests.get(API, timeout=60).json()
print("TITRE", d.get("title"), "| maj", d.get("last_modified"))
print("DESCRIPTION", (d.get("description") or "")[:3000])
res = d.get("resources", [])
for r in res:
    print("RES", r.get("title"), "|", r.get("format"), "|", r.get("filesize"), "|", r.get("url"))
pq = sorted([r for r in res if (r.get("format") or "").lower() == "parquet" or r.get("url", "").endswith(".parquet")],
            key=lambda r: r.get("filesize") or 1e18)
if pq:
    u = pq[0]["url"]
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    print("SCHEMA de", u)
    for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{u}')").fetchall():
        print("  COL", row[0], row[1])
    print("NB LIGNES", con.execute(f"SELECT count(*) FROM read_parquet('{u}')").fetchone())
    for row in con.execute(f"SELECT * FROM read_parquet('{u}') LIMIT 5").fetchall():
        print("  EX", row)
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{u}')").fetchall()]
    for c in cols:
        if any(k in c.lower() for k in ("typ", "equ")):
            print("VALEURS", c, con.execute(f"SELECT {c}, count(*) FROM read_parquet('{u}') GROUP BY 1 ORDER BY 1").fetchall()[:400])
for r in res:
    if (r.get("format") or "").lower() in ("csv", "txt") and (r.get("filesize") or 1e9) < 200000:
        print("CONTENU", r.get("title"), "\n", requests.get(r["url"], timeout=60).text[:6000])
