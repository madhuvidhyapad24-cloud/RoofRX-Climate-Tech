"""Hourly weather: Open-Meteo (real) with a clearly-labelled synthetic fallback."""
from __future__ import annotations

import numpy as np
import pandas as pd

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def synthetic_hot_week(days: int = 7, t_mean: float = 34.0, t_amp: float = 6.0,
                       peak_ghi: float = 900.0) -> pd.DataFrame:
    """Idealised hot-season weather. SYNTHETIC - label it as such in any report."""
    hours = np.arange(days * 24)
    h = hours % 24
    temp = t_mean + t_amp * np.sin(2 * np.pi * (h - 9) / 24.0)  # peak ~15:00
    ghi = np.clip(peak_ghi * np.sin(np.pi * (h - 6) / 12.0), 0, None)
    ghi[(h < 6) | (h > 18)] = 0.0
    return pd.DataFrame({"hour": hours, "temp_c": temp, "ghi_wm2": ghi, "source": "synthetic"})


def fetch_open_meteo(lat: float, lon: float, start: str, end: str,
                     timeout: float = 20.0) -> pd.DataFrame:
    """Fetch hourly temperature_2m and shortwave_radiation from Open-Meteo.

    Needs internet access. Raises on failure so the caller can fall back.
    NOTE: not exercised in the build sandbox (no outbound access) - test it on
    your own machine.
    """
    import requests

    r = requests.get(
        ARCHIVE_URL,
        params={
            "latitude": lat, "longitude": lon,
            "start_date": start, "end_date": end,
            "hourly": "temperature_2m,shortwave_radiation",
            "timezone": "auto",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    j = r.json()["hourly"]
    df = pd.DataFrame({
        "temp_c": j["temperature_2m"],
        "ghi_wm2": j["shortwave_radiation"],
    }).dropna().reset_index(drop=True)
    df.insert(0, "hour", np.arange(len(df)))
    df["source"] = "open-meteo"
    return df


def get_weather(lat: float, lon: float, start: str, end: str,
                use_live: bool = True) -> pd.DataFrame:
    """Live weather if possible, otherwise synthetic (with source column saying which)."""
    if use_live:
        try:
            df = fetch_open_meteo(lat, lon, start, end)
            if len(df) >= 48:
                return df
        except Exception:
            pass
    return synthetic_hot_week()
