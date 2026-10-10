"""Budgeted selection of roofs to treat.

benefit_i = hours_avoided_i * people_i        (people = 'occupants' column if given, else roof area as a PROXY)
cost_i    = area_i * cost_per_m2 + fixed_per_roof

Roof-level: greedy by benefit/cost until the budget is spent (a standard
knapsack heuristic, not a proven optimum).
Ward-level baseline: rank wards by mean modelled heat hours (the way a
ward-level tool would), then treat roofs inside the worst wards - picked in
random order within a ward - until the budget is spent. Averaged over seeds.
Random baseline: roofs in random order.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_cost_benefit(b: pd.DataFrame, cost_per_m2: float, fixed_per_roof: float = 0.0) -> pd.DataFrame:
    b = b.copy()
    weight = b["occupants"] if "occupants" in b.columns else b["area_m2"]  # people, else area as a proxy
    b["benefit"] = b["hours_avoided"] * weight
    b["cost"] = b["area_m2"] * cost_per_m2 + fixed_per_roof
    b["ratio"] = b["benefit"] / b["cost"]
    return b


def _take_in_order(b: pd.DataFrame, order: np.ndarray, budget: float) -> np.ndarray:
    """Walk 'order' (positional indices); take every roof that still fits."""
    chosen, spent = [], 0.0
    costs = b["cost"].to_numpy()
    for i in order:
        if costs[i] + spent <= budget:
            chosen.append(i)
            spent += costs[i]
    return np.array(chosen, dtype=int)


def roof_level(b: pd.DataFrame, budget: float) -> pd.DataFrame:
    # Many roofs tie on benefit per cost (hours are counted in whole hours), and tying on row
    # order would favour whichever ward is listed first. Break ties by the continuous indoor
    # temperature drop, then by larger roof area, then by row order.
    ratio = b["ratio"].to_numpy()
    top = ratio.max() if len(ratio) else 0.0
    key = np.round(ratio / top, 9) if top > 0 else ratio
    order = np.lexsort((np.arange(len(b)), -b["area_m2"].to_numpy(),
                        -b["mean_drop_c"].to_numpy(), -key))
    order = [i for i in order if b["benefit"].iloc[i] > 0]
    idx = _take_in_order(b, np.array(order, dtype=int), budget)
    sel = b.iloc[idx].copy()
    sel["rank"] = np.arange(1, len(sel) + 1)
    return sel


def ward_level(b: pd.DataFrame, budget: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ward_rank = b.groupby("ward")["hours_now"].mean().sort_values(ascending=False).index.tolist()
    order = []
    for w in ward_rank:
        pos = np.flatnonzero(b["ward"].to_numpy() == w)
        order.extend(rng.permutation(pos).tolist())
    idx = _take_in_order(b, np.array(order, dtype=int), budget)
    return b.iloc[idx].copy()


def random_level(b: pd.DataFrame, budget: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = _take_in_order(b, rng.permutation(len(b)), budget)
    return b.iloc[idx].copy()


def summarize(sel: pd.DataFrame) -> dict:
    return {
        "roofs": int(len(sel)),
        "cost": float(sel["cost"].sum()),
        "benefit": float(sel["benefit"].sum()),
        "hours_avoided_per_roof": float(sel["hours_avoided"].mean()) if len(sel) else 0.0,
    }


def compare(b: pd.DataFrame, budget: float, n_seeds: int = 50) -> dict:
    """Modelled benefit of the three strategies under the same budget."""
    roof = summarize(roof_level(b, budget))
    ward_b = [summarize(ward_level(b, budget, s))["benefit"] for s in range(n_seeds)]
    rand_b = [summarize(random_level(b, budget, s))["benefit"] for s in range(n_seeds)]
    ward_mean, rand_mean = float(np.mean(ward_b)), float(np.mean(rand_b))
    return {
        "roof_level": roof,
        "ward_level_benefit_mean": ward_mean,
        "ward_level_benefit_std": float(np.std(ward_b)),
        "random_benefit_mean": rand_mean,
        "gain_vs_ward_pct": 100.0 * (roof["benefit"] / ward_mean - 1.0) if ward_mean > 0 else float("nan"),
        "gain_vs_random_pct": 100.0 * (roof["benefit"] / rand_mean - 1.0) if rand_mean > 0 else float("nan"),
        "n_seeds": n_seeds,
    }
