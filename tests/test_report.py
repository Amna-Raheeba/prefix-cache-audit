"""Tests for the human-readable reports."""

from prefix_cache_audit.audit import analyze_trace
from prefix_cache_audit.cache import CacheSimulator
from prefix_cache_audit.canonical import canonicalize_trace
from prefix_cache_audit.evaluate import run_evaluation
from prefix_cache_audit.generate import build_trace
from prefix_cache_audit.models import DEFAULT_PRICING, DEFAULT_TTL_MINUTES
from prefix_cache_audit.report import (format_audit_report,
                                       format_evaluation_summary)


def _demo_report():
    trace = build_trace("mixed_kitchen_sink", 3, 12)
    audit = analyze_trace(trace)
    sim = CacheSimulator()
    logged = sim.simulate(trace.requests)
    canonical = sim.simulate(canonicalize_trace(trace).requests)
    return format_audit_report(trace, audit, logged, canonical,
                               DEFAULT_PRICING, DEFAULT_TTL_MINUTES)


def test_audit_report_contents():
    report = _demo_report()
    assert "mixed_kitchen_sink-3" in report
    assert "header_volatile" in report
    assert "Recoverable by canonical ordering" in report
    assert "masked behind an earlier divergence" in report


def test_audit_report_zero_reads_for_volatile_header():
    trace = build_trace("header_clock", 3, 12)
    audit = analyze_trace(trace)
    sim = CacheSimulator()
    logged = sim.simulate(trace.requests)
    assert logged.read_tokens == 0
    report = format_audit_report(
        trace, audit, logged,
        sim.simulate(canonicalize_trace(trace).requests),
        DEFAULT_PRICING, DEFAULT_TTL_MINUTES)
    assert "Cache reads: 0 tokens as logged" in report


def test_evaluation_summary_contents():
    results = run_evaluation(seeds=range(1))
    summary = format_evaluation_summary(results)
    assert "## Recovery by scenario family" in summary
    assert "## Breaker detection" in summary
    assert "pooled" in summary.lower()
    assert "header_volatile" in summary
