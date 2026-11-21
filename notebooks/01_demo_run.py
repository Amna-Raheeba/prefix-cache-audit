"""Notebook 01 -- demo run.

Build one trace from two contrasting families (a volatile header,
and the stable control), audit each, and print the divergence
report with the replayed recovery. Runnable as a plain script:
python notebooks/01_demo_run.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prefix_cache_audit.audit import analyze_trace
from prefix_cache_audit.cache import CacheSimulator
from prefix_cache_audit.canonical import canonicalize_trace
from prefix_cache_audit.generate import SCENARIOS, build_trace
from prefix_cache_audit.models import DEFAULT_PRICING, DEFAULT_TTL_MINUTES
from prefix_cache_audit.report import format_audit_report


def main():
    simulator = CacheSimulator()
    for family in ("header_clock", "stable"):
        trace = build_trace(family, 3, 12)
        audit = analyze_trace(trace)
        sim_logged = simulator.simulate(trace.requests)
        sim_canonical = simulator.simulate(
            canonicalize_trace(trace).requests)
        print(format_audit_report(
            trace, audit, sim_logged, sim_canonical,
            DEFAULT_PRICING, DEFAULT_TTL_MINUTES))
    print("Scenario families available: %s" % ", ".join(SCENARIOS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
