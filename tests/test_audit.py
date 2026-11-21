"""Tests for first-divergence attribution and classification."""

from prefix_cache_audit.audit import (analyze_trace,
                                      baseline_wasted_tokens,
                                      classify_pair, lcp_length)
from prefix_cache_audit.generate import build_trace
from prefix_cache_audit.models import Request, Segment


def test_lcp_length():
    assert lcp_length([1, 2, 3], [1, 2, 3]) == 3
    assert lcp_length([1, 2, 3], [1, 2, 4]) == 2
    assert lcp_length([1], [2]) == 0
    assert lcp_length([], [1]) == 0
    assert lcp_length([1, 2], [1, 2, 3]) == 2


def _pair(prev_seg, cur_seg):
    prev = Request(0, 0.0, [prev_seg])
    cur = Request(1, 1.0, [cur_seg])
    return prev, cur


def test_classify_header_volatile():
    prev, cur = _pair(
        Segment("header", "header", "session=s1 request=1 ts=t1"),
        Segment("header", "header", "session=s1 request=2 ts=t2"))
    assert classify_pair(prev, cur, cur.segments[0]) == "header_volatile"


def test_classify_header_real_change_is_not_volatile():
    prev, cur = _pair(
        Segment("header", "header", "session=s1 request=1 ts=t1"),
        Segment("header", "header", "session=s2 request=1 ts=t1"))
    assert classify_pair(prev, cur, cur.segments[0]) is None


def test_classify_tool_shuffle():
    prev, cur = _pair(
        Segment("tools", "tools",
                "tool:beta does things tool:alpha does other"),
        Segment("tools", "tools",
                "tool:alpha does other tool:beta does things"))
    assert classify_pair(prev, cur, cur.segments[0]) == \
        "tool_order_shuffle"


def test_classify_tool_content_change_is_not_shuffle():
    prev, cur = _pair(
        Segment("tools", "tools", "tool:alpha does things"),
        Segment("tools", "tools", "tool:alpha does other things"))
    assert classify_pair(prev, cur, cur.segments[0]) is None


def test_classify_json_reorder():
    prev, cur = _pair(
        Segment("json_blob", "json_blob", '{"a": 1, "b": 2}'),
        Segment("json_blob", "json_blob", '{"b": 2, "a": 1}'))
    assert classify_pair(prev, cur, cur.segments[0]) == \
        "json_key_reorder"


def test_classify_json_value_change_is_genuine():
    prev, cur = _pair(
        Segment("json_blob", "json_blob", '{"a": 1, "b": 2}'),
        Segment("json_blob", "json_blob", '{"b": 3, "a": 1}'))
    assert classify_pair(prev, cur, cur.segments[0]) is None


def test_classify_history_append_is_not_rewrite():
    prev, cur = _pair(
        Segment("history", "history", "user: one agent: two"),
        Segment("history", "history",
                "user: one agent: two user: three agent: four"))
    assert classify_pair(prev, cur, cur.segments[0]) is None


def test_classify_history_rewrite():
    prev, cur = _pair(
        Segment("history", "history", "user: one agent: two"),
        Segment("history", "history", "user: uno agent: two"))
    assert classify_pair(prev, cur, cur.segments[0]) == \
        "history_rewrite"


def test_classify_retrieved_before_static():
    prev = Request(0, 0.0, [
        Segment("retrieved", "retrieved", "chunk a"),
        Segment("system", "system", "rules")])
    cur = Request(1, 1.0, [
        Segment("retrieved", "retrieved", "chunk b"),
        Segment("system", "system", "rules")])
    assert classify_pair(prev, cur, cur.segments[0]) == \
        "retrieved_before_static"


def test_classify_retrieved_after_static_is_genuine():
    prev = Request(0, 0.0, [
        Segment("system", "system", "rules"),
        Segment("retrieved", "retrieved", "chunk a")])
    cur = Request(1, 1.0, [
        Segment("system", "system", "rules"),
        Segment("retrieved", "retrieved", "chunk b")])
    assert classify_pair(prev, cur, cur.segments[1]) is None


def test_stable_trace_predicts_nothing():
    audit = analyze_trace(build_trace("stable", 3, 12))
    assert all(p.predicted_class is None for p in audit.pairs)
    assert all(p.planted_class is None for p in audit.pairs)
    assert audit.class_counts == {}


def test_single_breaker_families_predict_exactly():
    for family in ("header_clock", "tool_shuffle", "json_churn",
                   "retrieved_first", "mixed_kitchen_sink"):
        audit = analyze_trace(build_trace(family, 3, 24))
        for pair in audit.pairs:
            assert pair.predicted_class == pair.planted_class, (
                family, pair.index, pair.predicted_class,
                pair.planted_class)


def test_header_clock_loses_whole_request():
    trace = build_trace("header_clock", 3, 8)
    audit = analyze_trace(trace)
    expected = sum(r.total_tokens for r in trace.requests[1:])
    assert audit.est_wasted_tokens == expected


def test_mixed_trace_reports_masked_breakers():
    audit = analyze_trace(build_trace("mixed_kitchen_sink", 3, 12))
    assert audit.masked_count > 0
    assert audit.class_counts == {"header_volatile": 11}


def test_baseline_underestimates_header_cascade():
    trace = build_trace("header_clock", 3, 12)
    audit = analyze_trace(trace)
    assert audit.baseline_wasted_tokens < audit.est_wasted_tokens


def test_baseline_overestimates_append_only_history():
    trace = build_trace("stable", 3, 12)
    audit = analyze_trace(trace)
    assert audit.baseline_wasted_tokens > audit.est_wasted_tokens
    assert baseline_wasted_tokens(trace) == \
        audit.baseline_wasted_tokens
