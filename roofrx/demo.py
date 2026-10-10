"""Command-line demo on SYNTHETIC data:  python -m roofrx.demo

Writes results/ranked_roofs.csv and results/comparison.png.
"""
from __future__ import annotations

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import data, pipeline, weather


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buildings", help="CSV of real buildings (default: synthetic city)")
    ap.add_argument("--budget", type=float, default=1_000_000.0, help="budget in currency units")
    ap.add_argument("--cost-per-m2", type=float, default=250.0)
    ap.add_argument("--threshold", type=float, default=35.0)
    ap.add_argument("--metric", choices=["degree_hours", "hours"], default="degree_hours",
                    help="heat measure: degree-hours above threshold (default) or whole hours above")
    ap.add_argument("--live-weather", action="store_true", help="try Open-Meteo first")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()

    b = data.load_buildings(a.buildings) if a.buildings else data.synthetic_city()
    w = weather.get_weather(b["lat"].mean(), b["lon"].mean(), "2025-04-20", "2025-04-30",
                            use_live=a.live_weather)
    r = pipeline.run(b, w, a.budget, a.cost_per_m2, threshold_c=a.threshold, metric=a.metric)

    os.makedirs(a.out, exist_ok=True)
    r["selected"].to_csv(os.path.join(a.out, "ranked_roofs.csv"), index=False)

    c = r["comparison"]
    print(f"data: {'user CSV' if a.buildings else 'SYNTHETIC city'} | weather: {r['weather_source']}")
    print(f"buildings: {len(b)} | budget: {a.budget:,.0f} | threshold: {a.threshold} C | measure: {a.metric}")
    print(f"roof-level : {c['roof_level']['roofs']} roofs, benefit {c['roof_level']['benefit']:,.0f}")
    print(f"ward-level : benefit {c['ward_level_benefit_mean']:,.0f} (+/- {c['ward_level_benefit_std']:,.0f}, {c['n_seeds']} seeds)")
    print(f"random     : benefit {c['random_benefit_mean']:,.0f}")
    print(f"roof vs ward: {c['gain_vs_ward_pct']:+.1f}% | roof vs random: {c['gain_vs_random_pct']:+.1f}% (modelled)")
    print("\nSanity check - modelled mean indoor drop from cool coating (C):")
    print(r["sanity"].round(2).to_string(index=False))

    fig, ax = plt.subplots(figsize=(6, 3.6))
    vals = [c["random_benefit_mean"], c["ward_level_benefit_mean"], c["roof_level"]["benefit"]]
    ax.bar(["Random", "Ward-level", "Roof-level"], vals, color=["#8d8d8d", "#00798c", "#d1495b"])
    ax.set_ylabel("Modelled benefit\n(heat avoided/day x m²)")
    ax.set_title("Same budget, three targeting strategies\n(modelled, " + ("synthetic data" if not a.buildings else "user data") + ")",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "comparison.png"), dpi=150)
    print(f"\nSaved: {a.out}/ranked_roofs.csv, {a.out}/comparison.png")


if __name__ == "__main__":
    main()
