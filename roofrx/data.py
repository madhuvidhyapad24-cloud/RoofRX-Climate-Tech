"""Building data: synthetic generator for demos + CSV loader for real data.

Required columns for real data (CSV):
    building_id, ward, lat, lon, area_m2, material   (metal|concrete|tile|other)
Optional:
    storeys (default 1)
    occupants (people per building; if present it replaces roof area as the benefit weight)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .materials import MATERIALS

REQUIRED = ["building_id", "ward", "lat", "lon", "area_m2", "material"]


def synthetic_city(n_wards: int = 8, per_ward: int = 150, seed: int = 0,
                   center=(11.341, 77.717)) -> pd.DataFrame:
    """SYNTHETIC buildings (not real data). Each ward has a different material mix
    and storey mix, so wards differ - but homes inside a ward also differ, which
    is what roof-level targeting exploits. Say 'synthetic' wherever you show it.
    """
    rng = np.random.default_rng(seed)
    rows = []
    mats = list(MATERIALS)
    bid = 0
    for w in range(n_wards):
        # ward-specific material and storey mix
        p = rng.dirichlet(np.array([3.0, 3.0, 1.5, 1.0]) * rng.uniform(0.5, 1.5, 4))
        p_multi = rng.uniform(0.05, 0.6)           # share of 2-storey homes
        wlat = center[0] + 0.02 * (w // 4) + rng.normal(0, 0.001)
        wlon = center[1] + 0.02 * (w % 4) + rng.normal(0, 0.001)
        for _ in range(per_ward):
            rows.append({
                "building_id": bid,
                "ward": f"W{w + 1}",
                "lat": wlat + rng.normal(0, 0.006),
                "lon": wlon + rng.normal(0, 0.006),
                "area_m2": float(np.clip(rng.lognormal(np.log(35), 0.45), 12, 200)),
                "material": rng.choice(mats, p=p),
                "storeys": 2 if rng.random() < p_multi else 1,
            })
            bid += 1
    return pd.DataFrame(rows)


def load_buildings(path_or_buffer) -> pd.DataFrame:
    df = pd.read_csv(path_or_buffer)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}. Required: {REQUIRED}")
    df = df.copy()
    if df.empty:
        raise ValueError("The CSV has no rows.")
    for c in ("lat", "lon", "area_m2"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
        n_bad = int(df[c].isna().sum())
        if n_bad:
            raise ValueError(f"Column '{c}' has {n_bad} missing or non-numeric values.")
    if not df["lat"].between(-90, 90).all() or not df["lon"].between(-180, 180).all():
        raise ValueError("lat must be in [-90, 90] and lon in [-180, 180].")
    if (df["area_m2"] <= 0).any():
        raise ValueError("area_m2 must be positive")
    if "occupants" in df.columns:
        df["occupants"] = pd.to_numeric(df["occupants"], errors="coerce")
        if df["occupants"].isna().any() or (df["occupants"] < 0).any():
            raise ValueError("Column 'occupants' must be a number of 0 or more in every row.")
    if df["building_id"].duplicated().any():
        raise ValueError("building_id must be unique (duplicates found).")
    df["material"] = df["material"].astype(str).str.lower().str.strip()
    bad = sorted(set(df["material"]) - set(MATERIALS))
    if bad:
        raise ValueError(f"Unknown materials {bad}; allowed: {list(MATERIALS)}")
    if "storeys" not in df.columns:
        df["storeys"] = 1
    df["storeys"] = pd.to_numeric(df["storeys"], errors="coerce").fillna(1).clip(lower=1)
    df["ward"] = df["ward"].astype(str)
    return df.reset_index(drop=True)
