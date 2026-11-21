"""Command line: demo audit of one trace, or the full evaluation."""

import argparse
import os
import sys

from .audit import analyze_trace
from .cache import CacheSimulator
from .canonical import canonicalize_trace
from .evaluate import run_evaluation, write_evaluation
from .generate import SCENARIOS, build_trace
from .models import DEFAULT_PRICING, DEFAULT_TTL_MINUTES
from .report import format_audit_report


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="prefix_cache_audit",
        description="Find which prompt segment breaks prefix-cache "
                    "reuse, and price the fix.")
    sub = parser.add_subparsers(dest="command")

    demo = sub.add_parser("demo", help="audit one generated trace")
    demo.add_argument("--family", default="mixed_kitchen_sink",
                      choices=list(SCENARIOS))
    demo.add_argument("--seed", type=int, default=3)
    demo.add_argument("--requests", type=int, default=12)

    evaluate = sub.add_parser("evaluate", help="run the seeded "
                                               "evaluation")
    evaluate.add_argument("--out", default="results",
                          help="output directory")
    evaluate.add_argument("--seeds", type=int, default=6,
                          help="seeds per scenario family (0..n-1)")

    args = parser.parse_args(argv)

    if args.command == "evaluate":
        results = run_evaluation(seeds=tuple(range(args.seeds)))
        paths = write_evaluation(results, args.out)
        print("Wrote evaluation for %d traces to %s" % (
            results["n_traces"], os.path.abspath(args.out)))
        for key in sorted(paths):
            print("  %s: %s" % (key, paths[key]))
        det = results["detection"]
        print("Breaker detection: P %.3f R %.3f F1 %.3f" % (
            det["precision"], det["recall"], det["f1"]))
        print("Pooled recoverable share of input cost: %.1f%%"
              % (results["pooled_recoverable_pct"] * 100.0))
        return 0

    # Default: demo.
    family = getattr(args, "family", "mixed_kitchen_sink")
    seed = getattr(args, "seed", 3)
    n_requests = getattr(args, "requests", 12)
    trace = build_trace(family, seed, n_requests)
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
