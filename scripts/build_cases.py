"""Build the shipped demo case: one mixed_kitchen_sink trace,
serialised with its planted ground truth, at data/demo_trace.json.

Run from the repository root:  python scripts/build_cases.py
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prefix_cache_audit.generate import build_trace, trace_to_dict

DEMO_FAMILY = "mixed_kitchen_sink"
DEMO_SEED = 3
DEMO_REQUESTS = 12


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    trace = build_trace(DEMO_FAMILY, DEMO_SEED, DEMO_REQUESTS)
    path = os.path.join(root, "data", "demo_trace.json")
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(trace_to_dict(trace), fh, indent=2)
    print("Wrote %s (%s, %d requests)" % (path, trace.trace_id,
                                         len(trace.requests)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
