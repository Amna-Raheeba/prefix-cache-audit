"""Seeded evaluation: score the auditor against planted truth.

For every scenario family and seed, one session trace is built,
audited, and replayed through the reference cache model twice --
as logged, and canonicalised. Three things are measured:

1. **Detection.** Per consecutive pair, the auditor's predicted
   breaker class vs the planted primary breaker: precision, recall
   and F1, overall and per class.
2. **Estimation error.** The auditor's LCP-based lost-token
   estimate (and the segment-granularity baseline's) against the
   cache model's actual non-read tokens; and each estimator's
   recoverable-cost estimate against the replayed cost difference.
3. **Recovery.** Per family, the share of as-logged input cost the
   canonical ordering recovers -- the audit's headline output,
   including the families where the honest answer is "almost
   none" (the control, and the TTL-bound family).
"""

import csv
import io
import json
import os

from .audit import analyze_trace
from .cache import CacheSimulator
from .canonical import canonicalize_trace
from .generate import SCENARIOS, build_trace
from .models import BREAKER_CLASSES, DEFAULT_PRICING, DEFAULT_TTL_MINUTES

FAMILIES = tuple(SCENARIOS)


def _rel_err(estimate, truth):
    if truth == 0:
        return 0.0 if estimate == 0 else 1.0
    return abs(estimate - truth) / abs(truth)


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def run_evaluation(seeds=range(6), n_requests=24,
                   pricing=DEFAULT_PRICING,
                   ttl_minutes=DEFAULT_TTL_MINUTES):
    simulator = CacheSimulator(pricing=pricing, ttl_minutes=ttl_minutes)
    per_class = dict(
        (cls, {"tp": 0, "fp": 0, "fn": 0}) for cls in BREAKER_CLASSES)
    n_pairs = 0
    masked_total = 0
    attribution = {}
    lost_mae = {"audit": [], "baseline": []}
    lost_rel = {"audit": [], "baseline": []}
    rec_rel = {"audit": [], "baseline": []}
    rec_abs = {"audit": [], "baseline": []}
    families = {}
    total_logged = 0.0
    total_canonical = 0.0
    n_traces = 0

    for family in FAMILIES:
        fam = {
            "traces": 0,
            "logged_cost": 0.0,
            "canonical_cost": 0.0,
            "recoverable_pct": 0.0,
            "est_wasted_tokens": 0,
            "true_lost_tokens": 0,
        }
        for seed in seeds:
            trace = build_trace(family, seed, n_requests)
            audit = analyze_trace(trace)
            canonical = canonicalize_trace(trace)
            audit_canonical = analyze_trace(canonical)
            sim_logged = simulator.simulate(trace.requests)
            sim_canonical = simulator.simulate(canonical.requests)
            usage_by_index = dict(
                (u.index, u) for u in sim_logged.per_request)
            true_lost = sum(
                u.lost_tokens for u in sim_logged.per_request[1:])

            for pair in audit.pairs:
                n_pairs += 1
                predicted = pair.predicted_class
                planted = pair.planted_class
                if planted is not None:
                    if predicted == planted:
                        per_class[planted]["tp"] += 1
                    else:
                        per_class[planted]["fn"] += 1
                if predicted is not None and predicted != planted:
                    per_class[predicted]["fp"] += 1
                key = planted if planted is not None else "unflagged_change"
                attribution[key] = attribution.get(key, 0) + (
                    usage_by_index[pair.index].lost_tokens)
            masked_total += audit.masked_count

            lost_mae["audit"].append(
                abs(audit.est_wasted_tokens - true_lost))
            lost_mae["baseline"].append(
                abs(audit.baseline_wasted_tokens - true_lost))
            lost_rel["audit"].append(
                _rel_err(audit.est_wasted_tokens, true_lost))
            lost_rel["baseline"].append(
                _rel_err(audit.baseline_wasted_tokens, true_lost))

            true_recoverable = (sim_logged.total_cost
                                - sim_canonical.total_cost)
            spread = pricing.write_rate - pricing.read_rate
            est_rec = {
                "audit": (audit.est_wasted_tokens
                          - audit_canonical.est_wasted_tokens) * spread,
                "baseline": (audit.baseline_wasted_tokens
                             - audit_canonical.baseline_wasted_tokens)
                            * spread,
            }
            for name in ("audit", "baseline"):
                rec_rel[name].append(
                    _rel_err(est_rec[name], true_recoverable))
                rec_abs[name].append(
                    abs(est_rec[name] - true_recoverable))

            fam["traces"] += 1
            fam["logged_cost"] += sim_logged.total_cost
            fam["canonical_cost"] += sim_canonical.total_cost
            fam["est_wasted_tokens"] += audit.est_wasted_tokens
            fam["true_lost_tokens"] += true_lost
            total_logged += sim_logged.total_cost
            total_canonical += sim_canonical.total_cost
            n_traces += 1
        if fam["logged_cost"]:
            fam["recoverable_pct"] = (
                (fam["logged_cost"] - fam["canonical_cost"])
                / fam["logged_cost"])
        families[family] = fam

    tp = sum(entry["tp"] for entry in per_class.values())
    fp = sum(entry["fp"] for entry in per_class.values())
    fn = sum(entry["fn"] for entry in per_class.values())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    per_class_out = {}
    for cls, entry in per_class.items():
        cls_p = (entry["tp"] / (entry["tp"] + entry["fp"])
                 if (entry["tp"] + entry["fp"]) else 0.0)
        cls_r = (entry["tp"] / (entry["tp"] + entry["fn"])
                 if (entry["tp"] + entry["fn"]) else 0.0)
        per_class_out[cls] = {
            "tp": entry["tp"], "fp": entry["fp"], "fn": entry["fn"],
            "precision": cls_p, "recall": cls_r,
        }

    total_attributed = sum(attribution.values())
    attribution_shares = dict(
        (key, (value / total_attributed if total_attributed else 0.0))
        for key, value in sorted(attribution.items()))

    return {
        "n_traces": n_traces,
        "n_pairs": n_pairs,
        "n_requests_per_trace": n_requests,
        "ttl_minutes": ttl_minutes,
        "pricing": {
            "read_rate": pricing.read_rate,
            "write_rate": pricing.write_rate,
            "base_rate": pricing.base_rate,
        },
        "detection": {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1,
            "per_class": per_class_out,
        },
        "estimator": {
            "audit": {
                "lost_token_mae": _mean(lost_mae["audit"]),
                "lost_token_rel_err": _mean(lost_rel["audit"]),
                "recoverable_rel_err": _mean(rec_rel["audit"]),
                "recoverable_abs_err": _mean(rec_abs["audit"]),
            },
            "baseline": {
                "lost_token_mae": _mean(lost_mae["baseline"]),
                "lost_token_rel_err": _mean(lost_rel["baseline"]),
                "recoverable_rel_err": _mean(rec_rel["baseline"]),
                "recoverable_abs_err": _mean(rec_abs["baseline"]),
            },
        },
        "families": families,
        "pooled_recoverable_pct": (
            (total_logged - total_canonical) / total_logged
            if total_logged else 0.0),
        "attribution_shares": attribution_shares,
        "masked_breakers": masked_total,
    }


def write_evaluation(results, out_dir):
    """Write evaluation.json / .csv / _summary.md; return paths."""
    from .report import format_evaluation_summary

    os.makedirs(out_dir, exist_ok=True)
    paths = {}

    json_path = os.path.join(out_dir, "evaluation.json")
    with io.open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, sort_keys=True)
    paths["json"] = json_path

    csv_path = os.path.join(out_dir, "evaluation.csv")
    with io.open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["family", "traces", "logged_cost",
                         "canonical_cost", "recoverable_pct",
                         "est_wasted_tokens", "true_lost_tokens"])
        for family in FAMILIES:
            fam = results["families"][family]
            writer.writerow([
                family, fam["traces"],
                "%.2f" % fam["logged_cost"],
                "%.2f" % fam["canonical_cost"],
                "%.4f" % fam["recoverable_pct"],
                fam["est_wasted_tokens"], fam["true_lost_tokens"],
            ])
    paths["csv"] = csv_path

    md_path = os.path.join(out_dir, "evaluation_summary.md")
    with io.open(md_path, "w", encoding="utf-8") as fh:
        fh.write(format_evaluation_summary(results))
    paths["summary"] = md_path
    return paths
