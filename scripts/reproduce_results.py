"""Headline-drift guard.

Re-runs the full seeded evaluation and compares the aggregate
headline numbers against the shipped results/evaluation.json.
Exits non-zero if any headline value moved by more than the
tolerance -- i.e. if the code no longer reproduces the published
results.

Run from the repository root:  python scripts/reproduce_results.py
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prefix_cache_audit.evaluate import FAMILIES, run_evaluation
from prefix_cache_audit.models import BREAKER_CLASSES

TOLERANCE = 0.02


def headline_values(results):
    det = results["detection"]
    values = {
        "precision": det["precision"],
        "recall": det["recall"],
        "f1": det["f1"],
        "pooled_recoverable_pct": results["pooled_recoverable_pct"],
        "masked_breakers": float(results["masked_breakers"]),
        "audit_lost_rel": results["estimator"]["audit"]["lost_token_rel_err"],
        "baseline_lost_rel": results["estimator"]["baseline"]["lost_token_rel_err"],
        "audit_rec_rel": results["estimator"]["audit"]["recoverable_rel_err"],
        "baseline_rec_rel": results["estimator"]["baseline"]["recoverable_rel_err"],
    }
    for family in FAMILIES:
        values["recoverable_%s" % family] = \
            results["families"][family]["recoverable_pct"]
    for cls in BREAKER_CLASSES:
        entry = det["per_class"][cls]
        values["recall_%s" % cls] = entry["recall"]
        values["precision_%s" % cls] = entry["precision"]
    for key, share in results["attribution_shares"].items():
        values["share_%s" % key] = share
    return values


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shipped_path = os.path.join(root, "results", "evaluation.json")
    with io.open(shipped_path, encoding="utf-8") as fh:
        shipped = json.load(fh)
    fresh = run_evaluation()
    expected = headline_values(shipped)
    actual = headline_values(fresh)
    failures = []
    for key in sorted(expected):
        if key not in actual:
            failures.append("%s missing from fresh run" % key)
        elif abs(expected[key] - actual[key]) > TOLERANCE:
            failures.append(
                "%s: shipped %.4f vs fresh %.4f"
                % (key, expected[key], actual[key])
            )
    if failures:
        print("HEADLINE DRIFT DETECTED:")
        for failure in failures:
            print("  " + failure)
        return 1
    print("All %d headline values reproduce within %.2f."
          % (len(expected), TOLERANCE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
