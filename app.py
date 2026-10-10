"""RoofRx Streamlit app.   streamlit run app.py

All analysis lives in the roofrx package (unit-tested). This file is UI only.
The app logic is smoke-tested with a stand-in for Streamlit (tests/test_app_smoke.py);
it has not been rendered in a real Streamlit session in the build sandbox.
"""
import io

import pandas as pd
import streamlit as st

from roofrx import data, pipeline, thermal, weather
from roofrx.materials import MATERIALS

st.set_page_config(page_title="RoofRx", layout="wide")
st.title("RoofRx: which roofs should get a cool coating first?")
st.caption("Indoor temperatures and benefits are MODELLED from assumed material "
           "parameters - not measured. Treat results as a prioritisation aid, not a forecast.")

with st.sidebar:
    st.header("Inputs")
    up = st.file_uploader("Buildings CSV (optional)", type="csv",
                          help="columns: building_id, ward, lat, lon, area_m2, material[, storeys]")
    budget = st.slider("Budget", 50_000, 5_000_000, 1_000_000, 50_000)
    cost_m2 = st.number_input("Coating cost per m²", 50.0, 2000.0, 250.0, 10.0)
    fixed = st.number_input("Fixed cost per roof", 0.0, 20000.0, 0.0, 100.0)
    thr = st.slider("Danger threshold, indoor °C (assumption)", 30.0, 40.0, 35.0, 0.5)
    metric_label = st.radio("Heat measure", ["Degree-hours above threshold", "Hours above threshold"],
                            help="Degree-hours sum how far indoor air is above the threshold. Whole hours "
                                 "tie easily and can rank a barely-hot roof level with a very hot one.")
    metric = "degree_hours" if metric_label.startswith("Degree") else "hours"
    live = st.checkbox("Try live Open-Meteo weather", value=False)


@st.cache_data(show_spinner=False)
def load(upload_bytes):
    if upload_bytes is None:
        return data.synthetic_city(), True
    return data.load_buildings(io.BytesIO(upload_bytes)), False


@st.cache_data(show_spinner=False)
def get_weather(lat, lon, live_flag):
    return weather.get_weather(lat, lon, "2025-04-20", "2025-04-30", use_live=live_flag)


@st.cache_data(show_spinner="Running thermal model...")
def score(buildings, weather_df, threshold, measure):
    # Slow step; only reruns when buildings, weather, threshold or measure change,
    # not when the budget or cost sliders move.
    return pipeline.score(buildings, weather_df, threshold, measure)


@st.cache_data(show_spinner=False)
def sanity(weather_df):
    return thermal.sanity_check(weather_df)


try:
    b, is_synth = load(up.getvalue() if up is not None else None)
except ValueError as e:
    st.error(f"Could not read the CSV: {e}")
    st.stop()

w = get_weather(float(b["lat"].mean()), float(b["lon"].mean()), live)
scored = score(b, w, thr, metric)
r = pipeline.select(scored, budget, cost_m2, fixed, n_seeds=30)
sel, c = r["selected"], r["comparison"]

if is_synth:
    st.warning("Showing a SYNTHETIC demo city. Upload a buildings CSV to analyse real data.")
st.info(f"Weather source: **{pipeline.weather_source(w)}**")
if live and pipeline.weather_source(w) != "open-meteo":
    st.warning("Live weather was not available, so synthetic weather is being used.")

if sel.empty:
    st.warning("The budget is too small to treat any roof. Increase the budget or lower the cost.")

def pct(x):
    return "n/a" if x != x else f"{x:+.1f}%"   # x != x is True only for NaN


k1, k2, k3, k4 = st.columns(4)
k1.metric("Roofs selected", f"{len(sel)} of {len(b)}")
k2.metric("Budget used", f"{sel['cost'].sum():,.0f}")
k3.metric("Roof-level vs ward-level", pct(c["gain_vs_ward_pct"]), help="modelled, same budget")
k4.metric("Roof-level vs random", pct(c["gain_vs_random_pct"]), help="modelled, same budget")

left, right = st.columns([3, 2])
with left:
    st.subheader("Map: selected roofs (red) vs others (grey)")
    chosen = b["building_id"].isin(set(sel["building_id"])).to_numpy()
    m = b[["lat", "lon"]].copy()
    m["color"] = "#bbbbbb"
    m["size"] = 12
    m.loc[chosen, "color"] = "#d1495b"
    m.loc[chosen, "size"] = 40
    st.map(m, latitude="lat", longitude="lon", color="color", size="size")
with right:
    st.subheader("Modelled benefit, same budget")
    # numbered labels keep this order (charts sort the x axis alphabetically)
    st.bar_chart(pd.DataFrame({
        "benefit": [c["random_benefit_mean"], c["ward_level_benefit_mean"], c["roof_level"]["benefit"]]
    }, index=["1 Random", "2 Ward-level", "3 Roof-level"]))
    st.caption("Benefit = heat avoided per day × roof area (or × occupants if your CSV has that column).")

st.subheader("Work order (ranked)")
cols = ["rank", "building_id", "ward", "material", "storeys", "area_m2",
        "hours_now", "hours_avoided", "mean_drop_c", "cost"]
st.dataframe(sel[cols].round(2), hide_index=True)
st.download_button("Download work order CSV", sel[cols].to_csv(index=False),
                   "roofrx_work_order.csv", mime="text/csv")

with st.expander("Model sanity check (plausibility, NOT validation)"):
    st.dataframe(sanity(w).round(2), hide_index=True)
    st.caption("Material parameters are assumed placeholders - replace with cited values.")
with st.expander("Assumed material parameters"):
    st.json({k: {x: v[x] for x in ("alpha", "u_roof")} for k, v in MATERIALS.items()})
