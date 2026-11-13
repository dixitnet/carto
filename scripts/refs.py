#!/usr/bin/env python3
"""Télécharge les référentiels Insee utiles au projet (gammes d'équipements de la BPE)."""
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "dixitnet-carto/1.0 (+https://github.com/dixitnet/carto)"}
GAMMES = "https://www.insee.fr/fr/metadonnees/source/fichier/BPE_gammes_equipements_2025.xlsx"

ref = ROOT / "data" / "ref"
ref.mkdir(parents=True, exist_ok=True)
r = requests.get(GAMMES, headers=UA, timeout=120)
r.raise_for_status()
(ref / "BPE_gammes_equipements_2025.xlsx").write_bytes(r.content)
feuilles = pd.read_excel(ref / "BPE_gammes_equipements_2025.xlsx", sheet_name=None, header=None, dtype=str)
for nom, df in feuilles.items():
    df = df.dropna(how="all").dropna(axis=1, how="all")
    cible = ref / f"bpe_gammes_2025_{nom.strip().lower().replace(' ', '_')}.csv"
    df.to_csv(cible, index=False, header=False)
    print(f"{nom} : {df.shape[0]} lignes x {df.shape[1]} colonnes -> {cible.name}", flush=True)
