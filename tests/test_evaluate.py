"""Tests for the seeded evaluation harness."""

import json
import os

from prefix_cache_audit.evaluate import run_evaluation, write_evaluation
from prefix_cache_audit.models import BREAKER_CLASSES


def test_evaluation_structure_small():
    results = run_evaluation(seeds=range(2))
    assert results["n_traces"] == 16
    assert results["n_pairs"] == 16 * 23
    det = results["detection"]
    for key in ("precision", "recall", "f1"):
        assert 0.0 <= det[key] <= 1.0
    for cls in BREAKER_CLASSES:
        assert cls in det["per_class"]
    assert set(results["families"]) == {
        "stable", "header_clock", "tool_shuffle", "json_churn",
        "history_rewrite", "retrieved_first", "mixed_kitchen_sink",
        "long_gap_ttl"}


def test_control_and_ttl_families_recover_nothing():
    results = run_evaluation(seeds=range(2))
    assert results["families"]["stable"]["recoverable_pct"] == 0.0
    assert results["families"]["long_gap_ttl"]["recoverable_pct"] == 0.0


def test_breaker_families_recover_substantially():
    results = run_evaluation(seeds=range(2))
    for family in ("header_clock", "tool_shuffle", "retrieved_first",
                   "mixed_kitchen_sink"):
        assert results["families"][family]["recoverable_pct"] > 0.4


def test_full_evaluation_detection_is_near_exact():
    results = run_evaluation()
    det = results["detection"]
    assert det["precision"] == 1.0
    assert det["recall"] >= 0.99
    assert det["fp"] == 0
    assert results["masked_breakers"] > 0


def test_audit_estimator_beats_baseline():
    results = run_evaluation(seeds=range(2))
    est = results["estimator"]
    assert (est["audit"]["lost_token_rel_err"]
            < est["baseline"]["lost_token_rel_err"])
    assert (est["audit"]["recoverable_rel_err"]
            < est["baseline"]["recoverable_rel_err"])


def test_attribution_shares_sum_to_one():
    results = run_evaluation(seeds=range(2))
    total = sum(results["attribution_shares"].values())
    assert abs(total - 1.0) < 1e-9
    assert results["attribution_shares"]["header_volatile"] > 0.2


def test_write_evaluation_outputs(tmp_path):
    results = run_evaluation(seeds=range(1))
    paths = write_evaluation(results, str(tmp_path))
    for key in ("json", "csv", "summary"):
        assert os.path.exists(paths[key])
    with open(paths["json"]) as fh:
        loaded = json.load(fh)
    assert loaded["n_traces"] == results["n_traces"]
    with open(paths["summary"]) as fh:
        assert "Recovery by scenario family" in fh.read()
