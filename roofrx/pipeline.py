"""Analysis pipeline, split so the app can cache the slow part.

score()  - thermal model per building (depends on buildings, weather, threshold only)
select() - cost/benefit, roof-level picks and baseline comparison (depends on budget/cost)
run()    - both, in one call (used by the demo CLI and tests)
"""
from __future__ import annotations

import pandas as pd

from . import optimizer, thermal


def score(buildings: pd.DataFrame, weather: pd.DataFrame, threshold_c: float = 35.0,
          metric: str = "degree_hours") -> pd.DataFrame:
    return thermal.building_heat(buildings, weather, threshold_c, metric)


def select(scored: pd.DataFrame, budget: float, cost_per_m2: float = 250.0,
           fixed_per_roof: float = 0.0, n_seeds: int = 50) -> dict:
    """Returns dict with: buildings (with cost/benefit), selected, comparison."""
    b = optimizer.add_cost_benefit(scored, cost_per_m2, fixed_per_roof)
    return {
        "buildings": b,
        "selected": optimizer.roof_level(b, budget),
        "comparison": optimizer.compare(b, budget, n_seeds),
    }


def weather_source(weather: pd.DataFrame) -> str:
    return str(weather["source"].iloc[0]) if "source" in weather else "unknown"


def run(buildings: pd.DataFrame, weather: pd.DataFrame, budget: float,
        cost_per_m2: float = 250.0, fixed_per_roof: float = 0.0,
        threshold_c: float = 35.0, n_seeds: int = 50, metric: str = "degree_hours") -> dict:
    """Returns dict with: buildings (scored), selected (roof-level picks),
    comparison (dict), sanity (DataFrame), weather_source (str)."""
    out = select(score(buildings, weather, threshold_c, metric), budget, cost_per_m2, fixed_per_roof, n_seeds)
    out["sanity"] = thermal.sanity_check(weather)
    out["weather_source"] = weather_source(weather)
    return out
