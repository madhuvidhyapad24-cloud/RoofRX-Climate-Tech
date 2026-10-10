"""Run with:  python -m unittest discover -s tests -v   (pytest also works)."""
import io
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roofrx import data, optimizer, pipeline, thermal, weather  # noqa: E402
from roofrx.materials import MATERIALS  # noqa: E402


class TestWeather(unittest.TestCase):
    def test_shape_and_night_has_no_sun(self):
        w = weather.synthetic_hot_week(days=3)
        self.assertEqual(len(w), 72)
        self.assertTrue((w.loc[w.hour % 24 == 2, "ghi_wm2"] == 0).all())
        self.assertGreater(w["ghi_wm2"].max(), 500)


class TestThermal(unittest.TestCase):
    def setUp(self):
        self.w = weather.synthetic_hot_week()

    def test_no_sun_means_indoor_follows_outdoor(self):
        w = self.w.copy()
        w["ghi_wm2"] = 0.0
        ind = thermal.simulate_indoor(w, 0.7, 3.0, 1)
        # mean indoor ~ mean outdoor when there is no solar gain
        self.assertAlmostEqual(ind[48:].mean(), w["temp_c"].iloc[48:].mean(), delta=0.5)

    def test_sun_heats_the_house(self):
        ind = thermal.simulate_indoor(self.w, 0.7, 3.0, 1)
        self.assertGreater(ind[48:].mean(), self.w["temp_c"].iloc[48:].mean())

    def test_lower_absorptance_is_cooler(self):
        hot = thermal.simulate_indoor(self.w, 0.8, 4.0, 1)
        cool = thermal.simulate_indoor(self.w, 0.3, 4.0, 1)
        self.assertTrue((cool[48:] <= hot[48:] + 1e-9).all())

    def test_more_storeys_dilutes_roof_effect(self):
        d = thermal.sanity_check(self.w)
        for m in MATERIALS:
            one = d[(d.material == m) & (d.storeys == 1)].mean_drop_c.iloc[0]
            two = d[(d.material == m) & (d.storeys == 2)].mean_drop_c.iloc[0]
            self.assertGreater(one, two)

    def test_hours_above_bounds(self):
        ind = thermal.simulate_indoor(self.w, 0.7, 3.0, 1)
        h = thermal.hours_above(ind, 35.0)
        self.assertTrue(((h >= 0) & (h <= 24)).all())
        self.assertEqual(thermal.hours_above(ind, 200.0)[0], 0.0)
        self.assertEqual(thermal.hours_above(ind, -50.0)[0], 24.0)


class TestData(unittest.TestCase):
    def test_synthetic_columns_and_materials(self):
        b = data.synthetic_city(n_wards=3, per_ward=20)
        self.assertEqual(len(b), 60)
        self.assertTrue(set(b.material) <= set(MATERIALS))
        for c in data.REQUIRED + ["storeys"]:
            self.assertIn(c, b.columns)

    def test_loader_validation(self):
        good = "building_id,ward,lat,lon,area_m2,material\n1,A,11,77,30,Metal\n"
        df = data.load_buildings(io.StringIO(good))
        self.assertEqual(df.material.iloc[0], "metal")
        self.assertEqual(df.storeys.iloc[0], 1)
        with self.assertRaises(ValueError):
            data.load_buildings(io.StringIO("building_id,ward\n1,A\n"))
        with self.assertRaises(ValueError):
            data.load_buildings(io.StringIO(good.replace("Metal", "thatch")))


class TestMeasures(unittest.TestCase):
    def setUp(self):
        self.b = data.synthetic_city(n_wards=3, per_ward=40, seed=2)
        self.w = weather.synthetic_hot_week()

    def test_degree_hours_nonnegative_and_zero_when_threshold_high(self):
        ind = thermal.simulate_indoor(self.w, 0.7, 3.0, 1)
        self.assertTrue((thermal.heat_load(ind, 35.0, metric="degree_hours") >= 0).all())
        self.assertEqual(thermal.heat_load(ind, 200.0, metric="degree_hours")[0], 0.0)

    def test_unknown_metric_rejected(self):
        ind = thermal.simulate_indoor(self.w, 0.7, 3.0, 1)
        with self.assertRaises(ValueError):
            thermal.heat_load(ind, 35.0, metric="nope")

    def test_degree_hours_separates_hot_roofs_from_marginal_ones(self):
        r = pipeline.run(self.b, self.w, 300_000, n_seeds=5, metric="degree_hours")
        sel = r["selected"]
        self.assertGreater(len(sel), 0)
        # the hottest class (single-storey metal) must be picked before cooler classes
        top = sel.iloc[0]
        self.assertEqual((top.material, top.storeys), ("metal", 1))

    def test_occupants_replace_area_as_weight(self):
        s = thermal.building_heat(self.b, self.w, 35.0)
        base = optimizer.add_cost_benefit(s, 250.0)
        s2 = s.copy()
        s2["occupants"] = 5.0
        occ = optimizer.add_cost_benefit(s2, 250.0)
        self.assertTrue(np.allclose(occ["benefit"], occ["hours_avoided"] * 5.0))
        self.assertTrue(np.allclose(base["benefit"], base["hours_avoided"] * base["area_m2"]))
        self.assertTrue(np.allclose(base["cost"], occ["cost"]))  # cost still depends on area

    def test_loader_occupants(self):
        hdr = "building_id,ward,lat,lon,area_m2,material,occupants\n"
        self.assertEqual(data.load_buildings(io.StringIO(hdr + "1,A,11,77,30,metal,6\n")).occupants.iloc[0], 6)
        with self.assertRaises(ValueError):
            data.load_buildings(io.StringIO(hdr + "1,A,11,77,30,metal,\n"))
        with self.assertRaises(ValueError):
            data.load_buildings(io.StringIO(hdr + "1,A,11,77,30,metal,-2\n"))


class TestLoaderStrict(unittest.TestCase):
    HDR = "building_id,ward,lat,lon,area_m2,material\n"

    def test_rejects_bad_values(self):
        cases = {
            "nan lat": "1,A,,77,30,metal\n",
            "text area": "1,A,11,77,big,metal\n",
            "lat range": "1,A,95,77,30,metal\n",
            "zero area": "1,A,11,77,0,metal\n",
            "dup ids": "1,A,11,77,30,metal\n1,A,11,77,30,tile\n",
        }
        for name, rows in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    data.load_buildings(io.StringIO(self.HDR + rows))
        with self.assertRaises(ValueError):
            data.load_buildings(io.StringIO(self.HDR))  # header only

    def test_ward_becomes_string(self):
        df = data.load_buildings(io.StringIO(self.HDR + "1,7,11,77,30,metal\n"))
        self.assertEqual(df.ward.iloc[0], "7")


class TestOptimizer(unittest.TestCase):
    def setUp(self):
        b = data.synthetic_city(n_wards=4, per_ward=60, seed=3)
        w = weather.synthetic_hot_week()
        s = thermal.building_heat(b, w, 35.0)
        self.b = optimizer.add_cost_benefit(s, cost_per_m2=250.0)

    def test_budget_never_exceeded(self):
        for budget in (0, 5_000, 100_000, 10**9):
            for fn in (optimizer.roof_level, optimizer.ward_level, optimizer.random_level):
                sel = fn(self.b, budget)
                self.assertLessEqual(sel["cost"].sum(), budget + 1e-6)

    def test_zero_budget_selects_nothing(self):
        self.assertEqual(len(optimizer.roof_level(self.b, 0)), 0)

    def test_no_duplicates(self):
        sel = optimizer.roof_level(self.b, 200_000)
        self.assertEqual(sel["building_id"].nunique(), len(sel))

    def test_roof_level_beats_baselines_on_this_data(self):
        c = optimizer.compare(self.b, 200_000, n_seeds=20)
        self.assertGreater(c["roof_level"]["benefit"], c["ward_level_benefit_mean"])
        self.assertGreater(c["roof_level"]["benefit"], c["random_benefit_mean"])

    def test_unlimited_budget_all_strategies_equal(self):
        c = optimizer.compare(self.b, 10**12, n_seeds=3)
        total = self.b["benefit"].sum()
        self.assertAlmostEqual(c["roof_level"]["benefit"], total, places=6)
        self.assertAlmostEqual(c["ward_level_benefit_mean"], total, places=6)


class TestPipeline(unittest.TestCase):
    def test_end_to_end(self):
        b = data.synthetic_city(n_wards=3, per_ward=40)
        r = pipeline.run(b, weather.synthetic_hot_week(), budget=100_000, n_seeds=5)
        self.assertEqual(r["weather_source"], "synthetic")
        self.assertIn("rank", r["selected"].columns)
        self.assertEqual(list(r["selected"]["rank"]), list(range(1, len(r["selected"]) + 1)))
        self.assertFalse(r["buildings"][["hours_now", "benefit", "cost"]].isna().any().any())

    def test_split_matches_run(self):
        b = data.synthetic_city(n_wards=3, per_ward=40)
        w = weather.synthetic_hot_week()
        full = pipeline.run(b, w, budget=80_000, n_seeds=5)
        part = pipeline.select(pipeline.score(b, w, 35.0), 80_000, n_seeds=5)
        self.assertEqual(list(full["selected"]["building_id"]), list(part["selected"]["building_id"]))
        self.assertAlmostEqual(full["comparison"]["roof_level"]["benefit"],
                               part["comparison"]["roof_level"]["benefit"])


if __name__ == "__main__":
    unittest.main()
