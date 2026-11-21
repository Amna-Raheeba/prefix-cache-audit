"""Tests for the data model: segments, requests, traces, pricing."""

from prefix_cache_audit.models import (BLOCK_TOKENS, DEFAULT_PRICING,
                                       Request, Segment, Trace,
                                       block_floor, tokenize)


def test_tokenize_splits_on_whitespace():
    assert tokenize("a b  c") == ["a", "b", "c"]
    assert tokenize("") == []
    assert tokenize("single") == ["single"]


def test_block_floor():
    assert block_floor(0) == 0
    assert block_floor(BLOCK_TOKENS - 1) == 0
    assert block_floor(BLOCK_TOKENS) == BLOCK_TOKENS
    assert block_floor(2 * BLOCK_TOKENS + 3) == 2 * BLOCK_TOKENS
    assert block_floor(100, 16) == 96


def test_segment_defaults_canonical_to_text():
    seg = Segment("s1", "system", "hello world")
    assert seg.canonical_text == "hello world"
    assert seg.breaker is None
    assert seg.token_count == 2


def test_segment_explicit_canonical():
    seg = Segment("s1", "header", "ts=now", canonical_text="ts=fixed",
                  breaker="header_volatile")
    assert seg.text == "ts=now"
    assert seg.canonical_text == "ts=fixed"
    assert seg.breaker == "header_volatile"


def test_request_token_stream_concatenates_in_order():
    req = Request(0, 0.0, [
        Segment("a", "system", "one two"),
        Segment("b", "user", "three"),
    ])
    assert req.token_stream() == ["one", "two", "three"]
    assert req.total_tokens == 3


def test_request_segment_lookup_and_span():
    req = Request(0, 0.0, [
        Segment("a", "system", "one two"),
        Segment("b", "user", "three four"),
    ])
    assert req.segment_by_id("b").kind == "user"
    assert req.segment_by_id("missing") is None
    assert req.segment_at_token(0).seg_id == "a"
    assert req.segment_at_token(1).seg_id == "a"
    assert req.segment_at_token(2).seg_id == "b"
    assert req.segment_at_token(99) is None


def test_trace_round_trip():
    trace = Trace("stable", 3, [
        Request(0, 0.0, [Segment("a", "system", "x y",
                                 breaker=None)]),
        Request(1, 1.5, [Segment("a", "system", "x y z")]),
    ])
    clone = Trace.from_dict(trace.to_dict())
    assert clone.to_dict() == trace.to_dict()
    assert clone.trace_id == "stable-3"


def test_pricing_defaults():
    assert DEFAULT_PRICING.read_rate == 0.30
    assert DEFAULT_PRICING.write_rate == 3.75
    assert DEFAULT_PRICING.base_rate == 3.00
