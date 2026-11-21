"""Audit the shipped demo trace and print its report.

Run from the repository root:  python examples/run_audit.py
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prefix_cache_audit.audit import analyze_trace
from prefix_cache_audit.cache import CacheSimulator
from prefix_cache_audit.canonical import canonicalize_trace
from prefix_cache_audit.generate import trace_from_dict
from prefix_cache_audit.models import DEFAULT_PRICING, DEFAULT_TTL_MINUTES
from prefix_cache_audit.report import format_audit_report


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "data", "demo_trace.json")
    with io.open(path, encoding="utf-8") as fh:
        trace = trace_from_dict(json.load(fh))
    audit = analyze_trace(trace)
    simulator = CacheSimulator()
    sim_logged = simulator.simulate(trace.requests)
    sim_canonical = simulator.simulate(
        canonicalize_trace(trace).requests)
    sys.stdout.write(format_audit_report(
        trace, audit, sim_logged, sim_canonical,
        DEFAULT_PRICING, DEFAULT_TTL_MINUTES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
