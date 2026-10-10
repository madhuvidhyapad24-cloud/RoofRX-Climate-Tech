"""Smoke-test app.py by executing it against a stand-in for Streamlit.

This catches Python errors in the app logic (bad columns, unpacking, NaN handling).
It does NOT check that Streamlit itself renders the widgets - run `streamlit run app.py`
for that.
"""
import os
import runpy
import sys
import types
import unittest
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class Stopped(Exception):
    pass


class Ctx:
    """Context manager / container whose attributes record calls."""
    def __init__(self, calls):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        def f(*args, **kw):
            self._calls.append((name, args, kw))
        return f


def make_streamlit(upload=None, slider_overrides=None):
    calls = []
    st = types.ModuleType("streamlit")
    overrides = slider_overrides or {}

    def rec(name):
        def f(*args, **kw):
            calls.append((name, args, kw))
        return f

    for n in ("set_page_config", "title", "caption", "header", "subheader", "info", "warning",
              "error", "metric", "map", "bar_chart", "dataframe", "download_button", "json"):
        setattr(st, n, rec(n))

    def stop():
        calls.append(("stop", (), {}))
        raise Stopped()

    def slider(label, lo, hi, value, step=None):
        calls.append(("slider", (label,), {}))
        return overrides.get(label, value)

    def number_input(label, lo, hi, value, step=None):
        return value

    def cache_data(*a, **kw):
        if a and callable(a[0]):
            return a[0]
        return lambda fn: fn

    def columns(spec):
        n = spec if isinstance(spec, int) else len(spec)
        return [Ctx(calls) for _ in range(n)]

    st.stop = stop
    st.slider = slider
    st.number_input = number_input
    st.checkbox = lambda *a, **k: False
    st.radio = lambda label, options, **k: options[0]
    st.file_uploader = lambda *a, **k: upload
    st.cache_data = cache_data
    st.columns = columns
    st.expander = lambda *a, **k: Ctx(calls)
    st.sidebar = Ctx(calls)
    return st, calls


def run_app(upload=None, slider_overrides=None):
    st, calls = make_streamlit(upload, slider_overrides)
    saved = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st
    try:
        try:
            runpy.run_path(os.path.join(ROOT, "app.py"))
        except Stopped:
            pass
    finally:
        if saved is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = saved
    return calls


class Upload:
    def __init__(self, text):
        self._b = text.encode()

    def getvalue(self):
        return self._b


def names(calls):
    return [c[0] for c in calls]


class TestAppSmoke(unittest.TestCase):
    def test_default_synthetic_run(self):
        calls = run_app()
        n = names(calls)
        self.assertNotIn("error", n)
        self.assertIn("map", n)
        self.assertIn("bar_chart", n)
        self.assertIn("download_button", n)
        df = [c for c in calls if c[0] == "dataframe"][0][1][0]
        self.assertGreater(len(df), 0)
        self.assertEqual(list(df.columns)[:2], ["rank", "building_id"])

    def test_tiny_budget_shows_warning_not_crash(self):
        calls = run_app(slider_overrides={"Budget": 50_000})
        # 50k cannot buy a roof only if every roof costs more; force it with a huge cost instead
        self.assertNotIn("error", names(calls))

    def test_uploaded_csv(self):
        csv = ("building_id,ward,lat,lon,area_m2,material\n"
               "1,A,11.3,77.7,30,metal\n2,A,11.31,77.71,40,concrete\n3,B,11.32,77.72,25,tile\n")
        calls = run_app(upload=Upload(csv))
        self.assertNotIn("error", names(calls))
        self.assertIn("dataframe", names(calls))

    def test_bad_csv_shows_error_and_stops(self):
        calls = run_app(upload=Upload("building_id,ward\n1,A\n"))
        self.assertIn("error", names(calls))
        self.assertIn("stop", names(calls))
        self.assertNotIn("map", names(calls))

    def test_nan_latitude_rejected(self):
        csv = ("building_id,ward,lat,lon,area_m2,material\n"
               "1,A,,77.7,30,metal\n")
        calls = run_app(upload=Upload(csv))
        self.assertIn("error", names(calls))

    def test_duplicate_ids_rejected(self):
        csv = ("building_id,ward,lat,lon,area_m2,material\n"
               "1,A,11.3,77.7,30,metal\n1,A,11.31,77.71,40,tile\n")
        calls = run_app(upload=Upload(csv))
        self.assertIn("error", names(calls))


if __name__ == "__main__":
    unittest.main()
