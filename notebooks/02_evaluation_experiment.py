"""Notebook 02 -- evaluation experiment.

Run the full seeded evaluation (all scenario families, six seeds
each) and print the headline numbers: recovery per family, breaker
detection, and estimator accuracy. Runnable as a plain script:
python notebooks/02_evaluation_experiment.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prefix_cache_audit.evaluate import run_evaluation


def main():
    results = run_evaluation()
    print("Traces: %d; pairs scored: %d"
          % (results["n_traces"], results["n_pairs"]))
    print("")
    print("Recovery by family (share of as-logged input cost "
          "recovered by canonical ordering):")
    for family, fam in results["families"].items():
        print("  %-19s %5.1f%%" % (family,
                                   fam["recoverable_pct"] * 100.0))
    print("  %-19s %5.1f%%" % ("POOLED",
                               results["pooled_recoverable_pct"] * 100.0))
    det = results["detection"]
    print("")
    print("Breaker detection: P %.3f R %.3f F1 %.3f"
          % (det["precision"], det["recall"], det["f1"]))
    for cls, entry in det["per_class"].items():
        print("  %-24s P %.3f R %.3f (tp %d, fp %d, fn %d)"
              % (cls, entry["precision"], entry["recall"],
                 entry["tp"], entry["fp"], entry["fn"]))
    est = results["estimator"]
    print("")
    print("Lost-token relative error: audit %.3f vs baseline %.3f"
          % (est["audit"]["lost_token_rel_err"],
             est["baseline"]["lost_token_rel_err"]))
    print("Recoverable-cost relative error: audit %.3f vs "
          "baseline %.3f"
          % (est["audit"]["recoverable_rel_err"],
             est["baseline"]["recoverable_rel_err"]))
    print("Masked breakers (flagged, hidden behind an earlier "
          "divergence): %d" % results["masked_breakers"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
