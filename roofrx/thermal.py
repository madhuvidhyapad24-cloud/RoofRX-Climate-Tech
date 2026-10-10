"""Lumped indoor-heat model (vectorised over buildings).

Per square metre of building footprint:

    T_sa  = T_out + alpha * I / h_out                      (sol-air temperature)
    C dT_in/dt = U_roof (T_sa - T_in) + H (T_out - T_in)

* C = c0 * storeys   : thermal capacity grows with the number of storeys
* H = h0 * storeys   : walls + ventilation conductance grows with storeys
* roof term is fixed per footprint m^2, so single-storey homes get a larger
  share of their heat from the roof - and benefit most from a cool roof.

This is a deliberately simple model. Indoor temperatures are MODELLED, not
measured, and the parameters in materials.py are assumed. Validate with
indoor sensors before making any real-world claim.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .materials import COOL_ALPHA, H_OUT, MATERIALS

C0 = 6.0e4      # J/(m^2 K) per storey, indoor air + light contents (assumed)
H0 = 2.5        # W/(m^2 K) per storey, walls + ventilation (assumed)
SPINUP_DAYS = 2  # discard the first days so initial conditions don't matter


def simulate_indoor(weather: pd.DataFrame, alpha, u_roof, storeys,
                    t_init: float | None = None) -> np.ndarray:
    """Return indoor temperature, shape (n_hours, n_buildings), hourly steps.

    alpha, u_roof, storeys: scalars or arrays of length n_buildings.
    Integrated with 6 sub-steps per hour (explicit Euler is stable here).
    """
    alpha = np.atleast_1d(np.asarray(alpha, dtype=float))
    u_roof = np.atleast_1d(np.asarray(u_roof, dtype=float))
    storeys = np.atleast_1d(np.asarray(storeys, dtype=float))
    n = max(alpha.size, u_roof.size, storeys.size)
    alpha, u_roof, storeys = (np.broadcast_to(a, (n,)) for a in (alpha, u_roof, storeys))

    C = C0 * storeys
    H = H0 * storeys
    t_out = weather["temp_c"].to_numpy(float)
    ghi = weather["ghi_wm2"].to_numpy(float)

    sub = 6
    dt = 3600.0 / sub
    t_in = np.full(n, t_out[0] if t_init is None else t_init, dtype=float)
    out = np.empty((len(t_out), n))
    for i in range(len(t_out)):
        t_sa = t_out[i] + alpha * ghi[i] / H_OUT
        for _ in range(sub):
            dT = (u_roof * (t_sa - t_in) + H * (t_out[i] - t_in)) / C
            t_in = t_in + dt * dT
        out[i] = t_in
    return out


def hours_above(indoor: np.ndarray, threshold_c: float,
                spinup_days: int = SPINUP_DAYS) -> np.ndarray:
    """Average hours/day above threshold per building, after spin-up."""
    steady = indoor[spinup_days * 24:]
    days = steady.shape[0] / 24.0
    return (steady > threshold_c).sum(axis=0) / days


def heat_load(indoor: np.ndarray, threshold_c: float, spinup_days: int = SPINUP_DAYS,
              metric: str = "hours") -> np.ndarray:
    """Heat per day per building after spin-up.

    metric="hours"         : hours/day indoor air is above the threshold
    metric="degree_hours"  : degree-hours/day above the threshold (how far above, summed)
    Whole-hour counts tie easily and saturate for very hot roofs; degree-hours do not.
    """
    steady = indoor[spinup_days * 24:]
    days = steady.shape[0] / 24.0
    if metric == "hours":
        return (steady > threshold_c).sum(axis=0) / days
    if metric == "degree_hours":
        return np.clip(steady - threshold_c, 0, None).sum(axis=0) / days
    raise ValueError("metric must be 'hours' or 'degree_hours'")


def building_heat(buildings: pd.DataFrame, weather: pd.DataFrame,
                  threshold_c: float = 35.0, metric: str = "degree_hours") -> pd.DataFrame:
    """Add modelled heat metrics for current roofs and for a cool-roof retrofit.

    Adds: hours_now, hours_cool, hours_avoided (heat per day above threshold; hours or
          degree-hours depending on `metric`),
          mean_now_c, mean_cool_c, mean_drop_c (mean indoor temp, steady state).
    """
    b = buildings.copy()
    mats = b["material"].map(MATERIALS)
    alpha = np.array([m["alpha"] for m in mats])
    u_roof = np.array([m["u_roof"] for m in mats])
    storeys = b["storeys"].to_numpy(float)

    now = simulate_indoor(weather, alpha, u_roof, storeys)
    cool = simulate_indoor(weather, np.minimum(alpha, COOL_ALPHA), u_roof, storeys)

    b["hours_now"] = heat_load(now, threshold_c, metric=metric)
    b["hours_cool"] = heat_load(cool, threshold_c, metric=metric)
    b["hours_avoided"] = (b["hours_now"] - b["hours_cool"]).clip(lower=0)
    s = SPINUP_DAYS * 24
    b["mean_now_c"] = now[s:].mean(axis=0)
    b["mean_cool_c"] = cool[s:].mean(axis=0)
    b["mean_drop_c"] = b["mean_now_c"] - b["mean_cool_c"]
    return b


def sanity_check(weather: pd.DataFrame) -> pd.DataFrame:
    """Mean indoor-temperature drop from a cool coating, by material and storeys.

    Report this honestly. It is a plausibility check on the model, NOT validation.
    """
    rows = []
    for name, m in MATERIALS.items():
        for st in (1, 2):
            now = simulate_indoor(weather, m["alpha"], m["u_roof"], st)
            cool = simulate_indoor(weather, min(m["alpha"], COOL_ALPHA), m["u_roof"], st)
            s = SPINUP_DAYS * 24
            rows.append({
                "material": name, "storeys": st,
                "mean_drop_c": float((now[s:] - cool[s:]).mean()),
                "peak_drop_c": float((now[s:] - cool[s:]).max()),
            })
    return pd.DataFrame(rows)
