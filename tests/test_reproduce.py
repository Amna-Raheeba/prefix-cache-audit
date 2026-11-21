"""The shipped results must reproduce: run the drift guard."""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_guard():
    path = os.path.join(ROOT, "scripts", "reproduce_results.py")
    spec = importlib.util.spec_from_file_location("reproduce_results",
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_headline_values_reproduce():
    guard = _load_guard()
    assert guard.main() == 0
