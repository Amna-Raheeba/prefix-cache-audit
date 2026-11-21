"""Tests for canonicalisation."""

import json

from prefix_cache_audit.canonical import (canonicalize_request,
                                          canonicalize_trace)
from prefix_cache_audit.generate import build_trace
from prefix_cache_audit.models import CANONICAL_RANK, Request, Segment


def test_segments_sorted_by_rank():
    req = Request(0, 0.0, [
        Segment("user", "user", "question"),
        Segment("history", "history", "turns"),
        Segment("system", "system", "rules"),
        Segment("header", "header", "meta"),
    ])
    canon = canonicalize_request(req)
    ranks = [CANONICAL_RANK[s.kind] for s in canon.segments]
    assert ranks == sorted(ranks)
    assert canon.segments[0].kind == "header"


def test_canonical_text_replaces_logged_text():
    trace = build_trace("header_clock", 3, 4)
    canon = canonicalize_trace(trace)
    for request in canon.requests:
        header = request.segment_by_id("header")
        assert "request=0" in header.text
        assert "ts=2026-01-01T00:00:00Z" in header.text


def test_tools_sorted_by_name():
    trace = build_trace("tool_shuffle", 3, 4)
    canon = canonicalize_trace(trace)
    tools_text = canon.requests[0].segment_by_id("tools").text
    names = [tok[5:] for tok in tools_text.split()
             if tok.startswith("tool:")]
    assert names == sorted(names)


def test_json_keys_sorted():
    trace = build_trace("json_churn", 3, 4)
    canon = canonicalize_trace(trace)
    text = canon.requests[0].segment_by_id("json_blob").text
    keys = list(json.loads(text).keys())
    assert keys == sorted(keys)


def test_history_canonical_chain_is_append_only():
    trace = build_trace("history_rewrite", 3, 8)
    canon = canonicalize_trace(trace)
    histories = [r.segment_by_id("history").text.split()
                 for r in canon.requests]
    for prev, cur in zip(histories, histories[1:]):
        assert cur[:len(prev)] == prev


def test_canonicalisation_is_idempotent():
    trace = build_trace("mixed_kitchen_sink", 3, 6)
    once = canonicalize_trace(trace)
    twice = canonicalize_trace(once)
    assert once.to_dict() == twice.to_dict()


def test_canonicalisation_clears_breaker_flags():
    trace = build_trace("mixed_kitchen_sink", 3, 4)
    canon = canonicalize_trace(trace)
    for request in canon.requests:
        for segment in request.segments:
            assert segment.breaker is None


def test_canonicalisation_preserves_timing_and_tokens():
    trace = build_trace("tool_shuffle", 3, 6)
    canon = canonicalize_trace(trace)
    for logged, fixed in zip(trace.requests, canon.requests):
        assert logged.at_minutes == fixed.at_minutes
        assert logged.index == fixed.index
        assert logged.total_tokens == fixed.total_tokens
