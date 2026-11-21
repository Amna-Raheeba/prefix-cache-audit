"""Tests for the seeded trace generator and its planted truth."""

import json

import pytest

from prefix_cache_audit.generate import SCENARIOS, build_trace

FAMILIES = list(SCENARIOS)


def test_all_families_build():
    for family in FAMILIES:
        trace = build_trace(family, 3, 24)
        assert len(trace.requests) == 24
        assert trace.family == family


def test_unknown_family_raises():
    with pytest.raises(ValueError):
        build_trace("no_such_family", 0)


def test_deterministic_per_seed():
    first = build_trace("mixed_kitchen_sink", 3, 12).to_dict()
    second = build_trace("mixed_kitchen_sink", 3, 12).to_dict()
    assert first == second
    other = build_trace("mixed_kitchen_sink", 4, 12).to_dict()
    assert first != other


def test_timestamps_increase():
    for family in FAMILIES:
        trace = build_trace(family, 1, 12)
        times = [r.at_minutes for r in trace.requests]
        assert times == sorted(times)
        assert times[0] == 0.0


def test_long_gap_spacing_exceeds_ttl():
    trace = build_trace("long_gap_ttl", 2, 12)
    gaps = [b.at_minutes - a.at_minutes
            for a, b in zip(trace.requests, trace.requests[1:])]
    assert all(gap >= 6.0 for gap in gaps)


def test_stable_family_has_no_breakers():
    trace = build_trace("stable", 3, 12)
    for request in trace.requests:
        for segment in request.segments:
            assert segment.breaker is None
            assert segment.canonical_text == segment.text


def test_stable_header_is_constant():
    trace = build_trace("stable", 3, 12)
    headers = [r.segment_by_id("header").text for r in trace.requests]
    assert len(set(headers)) == 1


def test_header_clock_flags_and_distinct_headers():
    trace = build_trace("header_clock", 3, 12)
    headers = [r.segment_by_id("header") for r in trace.requests]
    assert all(h.breaker == "header_volatile" for h in headers)
    assert len(set(h.text for h in headers)) == 12
    assert all(h.canonical_text.endswith("ts=2026-01-01T00:00:00Z")
               for h in headers)


def test_tool_shuffle_same_multiset_new_order():
    trace = build_trace("tool_shuffle", 3, 24)
    canonical = trace.requests[0].segment_by_id("tools").canonical_text
    for request in trace.requests:
        seg = request.segment_by_id("tools")
        assert seg.breaker == "tool_order_shuffle"
        assert sorted(seg.text.split()) == sorted(canonical.split())
    orders = [r.segment_by_id("tools").text for r in trace.requests]
    assert len(set(orders)) > 1


def test_json_flags_only_pure_reorders():
    flagged = 0
    for seed in range(6):
        trace = build_trace("json_churn", seed, 24)
        for request in trace.requests:
            seg = request.segment_by_id("json_blob")
            if seg.breaker == "json_key_reorder":
                flagged += 1
                assert json.loads(seg.text) == json.loads(
                    seg.canonical_text)
                assert seg.text != seg.canonical_text
    assert flagged > 20


def test_history_rewrite_canonical_is_append_chain():
    trace = build_trace("history_rewrite", 3, 12)
    canonicals = [r.segment_by_id("history").canonical_text.split()
                  for r in trace.requests]
    for prev, cur in zip(canonicals, canonicals[1:]):
        assert cur[:len(prev)] == prev
    for request in trace.requests:
        assert request.segment_by_id("history").breaker == \
            "history_rewrite"


def test_retrieved_first_layout():
    trace = build_trace("retrieved_first", 3, 4)
    kinds = [s.kind for s in trace.requests[0].segments]
    assert kinds.index("retrieved") < kinds.index("system")
    assert kinds.index("retrieved") < kinds.index("tools")
    seg = trace.requests[0].segment_by_id("retrieved")
    assert seg.breaker == "retrieved_before_static"


def test_mixed_layout_order():
    trace = build_trace("mixed_kitchen_sink", 3, 4)
    kinds = [s.kind for s in trace.requests[0].segments]
    assert kinds == ["header", "retrieved", "system", "tools",
                     "json_blob", "history", "volatile", "user"]


def test_default_layout_matches_canonical_ranks():
    from prefix_cache_audit.models import CANONICAL_RANK
    trace = build_trace("json_churn", 3, 4)
    kinds = [s.kind for s in trace.requests[0].segments]
    ranks = [CANONICAL_RANK[k] for k in kinds]
    assert ranks == sorted(ranks)


def test_history_grows_by_one_turn_per_request():
    trace = build_trace("stable", 3, 6)
    counts = [r.segment_by_id("history").text.count("user:")
              for r in trace.requests]
    assert counts == [1, 2, 3, 4, 5, 6]
