"""Smoke test: the Streamlit dashboard runs without exceptions."""

import os

from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_dashboard_runs():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"))
    at.run(timeout=180)
    assert not at.exception
    assert at.title[0].value == "Prefix Cache Audit"
