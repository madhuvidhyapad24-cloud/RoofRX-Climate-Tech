"""Check that web/engine.js gives the same answers as the Python package.

    python web/check_parity.py

Runs the JS engine in node on web/data/synthetic_city.json, runs the Python
pipeline on the same rows, and compares everything deterministic. The random
baselines use different random-number generators, so those are compared only
loosely (they should agree within sampling noise).
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from roofrx import optimizer, pipeline, thermal, weather  # noqa: E402
from roofrx.materials import MATERIALS  # noqa: E402

BUDGET, COST, FIXED, THR = 1_000_000.0, 250.0, 0.0, 35.0

NODE = r"""
const R = require(process.argv[1] + '/engine.js');
const d = JSON.parse(require('fs').readFileSync(process.argv[1] + '/data/synthetic_city.json', 'utf8'));
const b = R.fromRows(d.rows, d.wards);
const eng = R.prepare(b);
const METRIC = process.argv[2] || 'hours';
if (process.argv[3] === 'people') b.people = Float64Array.from(d.rows.map(r => Math.floor(r[4] / 8 + 0.5) + 1));
const sc = R.scoreAt(eng, %THR%, METRIC);
const cb = R.costBenefit(b, sc.avoided, %COST%, %FIXED%);
const order = R.rankRoofs(cb, b, eng.meanDrop);
const take = []; R.walk(order, cb.cost, cb.benefit, %BUDGET%, take);
const orders = R.baselineOrders(b, sc.hNow, 50);
const cmp = R.compareAt(order, orders, cb, %BUDGET%);
const wx = {};
const ok24 = (n, f) => Array.from({length: n}, (_, i) => f(i));
try { R.weatherFromArrays(ok24(48, () => 30), ok24(48, () => 0)); wx.short = null; } catch (e) { wx.short = e.message; }
try { R.weatherFromArrays(ok24(72, () => 90), ok24(72, () => 0)); wx.range = null; } catch (e) { wx.range = e.message; }
try { const w = R.weatherFromArrays(ok24(80, i => i === 5 ? null : 30), ok24(80, () => 100)); wx.fill = [w.n, w.temp[5]]; } catch (e) { wx.fill = e.message; }
const hdr2 = 'building_id,ward,lat,lon,area_m2,material,occupants\n';
try { R.parseCsv(hdr2 + '1,A,11,77,30,metal,\n'); wx.occ = null; } catch (e) { wx.occ = e.message; }
const okOcc = R.parseCsv(hdr2 + '1,A,11,77,30,metal,6\n'); wx.occOk = Array.from(okOcc.people);
// csv checks
const errs = {};
const hdr = 'building_id,ward,lat,lon,area_m2,material\n';
const cases = {
  ok: hdr + '1,A,11,77,30,Metal\n',
  nanlat: hdr + '1,A,,77,30,metal\n',
  dup: hdr + '1,A,11,77,30,metal\n1,A,11,77,30,tile\n',
  badmat: hdr + '1,A,11,77,30,thatch\n',
  zero: hdr + '1,A,11,77,0,metal\n',
  cols: 'building_id,ward\n1,A\n'
};
for (const k in cases) { try { R.parseCsv(cases[k]); errs[k] = null; } catch (e) { errs[k] = e.message; } }
console.log(JSON.stringify({
  hNow: Array.from(sc.hNow), avoided: Array.from(sc.avoided), meanDrop: Array.from(eng.meanDrop),
  selectedIds: take.map(i => b.id[i]), roofBenefit: cmp.roof.benefit, roofCount: cmp.roof.count,
  wardMean: cmp.wardMean, wardStd: cmp.wardStd, randMean: cmp.randMean,
  gainWard: cmp.gainWard, gainRand: cmp.gainRand, sanity: R.sanity(), csv: errs, wx: wx
}));
"""


def run_js(metric, people):
    js = (NODE.replace("%THR%", str(THR)).replace("%COST%", str(COST))
          .replace("%FIXED%", str(FIXED)).replace("%BUDGET%", str(BUDGET)))
    args = ["node", "-e", js, HERE, metric] + (["people"] if people else [])
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode:
        print(res.stderr)
        sys.exit(1)
    return json.loads(res.stdout)


def main():
    d = json.load(open(os.path.join(HERE, "data", "synthetic_city.json")))
    mats = d["materials"]
    base = pd.DataFrame(d["rows"], columns=["building_id", "wi", "lat", "lon", "area_m2", "mi", "storeys"])
    base["ward"] = [d["wards"][i] for i in base.wi]
    base["material"] = [mats[i] for i in base.mi]
    w = weather.synthetic_hot_week()
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name + (" | " + detail if detail else ""))

    scenarios = [("hours", False, "hours_now"), ("degree_hours", True, "degree-hours + occupants")]
    first = None
    for metric, people, label in scenarios:
        print(f"\n== {label} ==")
        j = run_js("degree" if metric == "degree_hours" else "hours", people)
        first = first or j
        df = base.copy()
        if people:
            df["occupants"] = np.floor(df.area_m2 / 8 + 0.5) + 1
        r = pipeline.run(df, w, BUDGET, COST, FIXED, THR, n_seeds=50, metric=metric)
        b = r["buildings"]
        for key, col in (("hNow", "hours_now"), ("avoided", "hours_avoided"), ("meanDrop", "mean_drop_c")):
            diff = float(np.max(np.abs(np.array(j[key]) - b[col].to_numpy())))
            check(f"{col} matches", diff < 1e-8, f"max abs diff {diff:.2e}")
        py_ids = [int(x) for x in r["selected"]["building_id"]]
        check("same roofs selected, same order", py_ids == j["selectedIds"], f"{len(py_ids)} vs {len(j['selectedIds'])}")
        pyb = r["comparison"]["roof_level"]["benefit"]
        check("roof-level benefit matches", abs(pyb - j["roofBenefit"]) < 1e-6 * max(pyb, 1), f"py {pyb:.4f} js {j['roofBenefit']:.4f}")
        pw = r["comparison"]["ward_level_benefit_mean"]
        pr = r["comparison"]["random_benefit_mean"]
        check("ward baseline within sampling noise", abs(pw - j["wardMean"]) < 3 * max(j["wardStd"], 1),
              f"py {pw:.0f} js {j['wardMean']:.0f} (sd {j['wardStd']:.0f})")
        check("random baseline within 3%", abs(pr - j["randMean"]) / pr < 0.03, f"py {pr:.0f} js {j['randMean']:.0f}")
        print(f"     gain vs ward  py {r['comparison']['gain_vs_ward_pct']:+.2f}%  js {j['gainWard']:+.2f}%")
        print(f"     gain vs random py {r['comparison']['gain_vs_random_pct']:+.2f}%  js {j['gainRand']:+.2f}%")

    print("\n== shared checks ==")
    s = r["sanity"].set_index(["material", "storeys"])
    sd = max(abs(s.loc[(x["material"], x["storeys"]), "mean_drop_c"] - x["mean"]) for x in first["sanity"])
    check("sanity table matches", sd < 1e-9, f"max diff {sd:.2e}")
    c = first["csv"]
    check("csv: valid file accepted", c["ok"] is None)
    for k in ("nanlat", "dup", "badmat", "zero", "cols"):
        check(f"csv: {k} rejected", c[k] is not None, str(c[k]))
    x = first["wx"]
    check("weather: too short rejected", x["short"] is not None, str(x["short"]))
    check("weather: out-of-range rejected", x["range"] is not None, str(x["range"]))
    check("weather: small gap filled, length trimmed to whole days", x["fill"] == [72, 30], str(x["fill"]))
    check("csv: blank occupants rejected", x["occ"] is not None, str(x["occ"]))
    check("csv: occupants read", x["occOk"] == [6])

    print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
