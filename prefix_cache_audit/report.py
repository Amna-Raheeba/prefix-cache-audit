"""Human-readable reports: the demo audit and the evaluation summary."""

from .models import BREAKER_CLASSES


def _label(value):
    return value if value is not None else "-"


def format_audit_report(trace, audit, sim_logged, sim_canonical,
                        pricing, ttl_minutes):
    """The demo report: one trace, its divergences, and its price."""
    lines = []
    lines.append("Prefix Cache Audit -- demo report")
    lines.append("=================================")
    total_tokens = sum(r.total_tokens for r in trace.requests)
    lines.append("Trace: %s (%d requests, %d tokens as logged)"
                 % (trace.trace_id, len(trace.requests), total_tokens))
    lines.append("Pricing: read %.2f / write %.2f / base %.2f per "
                 "token; TTL %.1f min"
                 % (pricing.read_rate, pricing.write_rate,
                    pricing.base_rate, ttl_minutes))
    lines.append("")
    lines.append("Per-request divergence (against the previous request):")
    lines.append(" req  at(min)   lcp  lost~  diverging   "
                 "predicted              planted")
    for pair in audit.pairs:
        lines.append(" %3d  %7.2f  %4d  %5d  %-10s  %-21s  %s" % (
            pair.index,
            trace.requests[pair.index].at_minutes,
            pair.lcp_tokens,
            pair.lost_tokens_est,
            pair.diverging_kind or "-",
            _label(pair.predicted_class),
            _label(pair.planted_class),
        ))
    lines.append("")
    n_breaker_pairs = sum(
        1 for pair in audit.pairs if pair.predicted_class is not None)
    lines.append("Breaker pairs: %d of %d; flagged breakers masked "
                 "behind an earlier divergence: %d"
                 % (n_breaker_pairs, len(audit.pairs),
                    audit.masked_count))
    if audit.class_counts:
        counts = ", ".join(
            "%s x%d" % (cls, audit.class_counts[cls])
            for cls in BREAKER_CLASSES if cls in audit.class_counts)
        lines.append("Attributed classes: %s" % counts)
    lines.append("Estimated lost tokens: %d (segment-granularity "
                 "baseline: %d)"
                 % (audit.est_wasted_tokens,
                    audit.baseline_wasted_tokens))
    lines.append("Cache-model lost tokens (requests 2..n): %d"
                 % sum(u.lost_tokens for u in sim_logged.per_request[1:]))
    lines.append("")
    recoverable = sim_logged.total_cost - sim_canonical.total_cost
    pct = (recoverable / sim_logged.total_cost
           if sim_logged.total_cost else 0.0)
    lines.append("Replay: as-logged cost %.1f; canonical cost %.1f"
                 % (sim_logged.total_cost, sim_canonical.total_cost))
    lines.append("Recoverable by canonical ordering: %.1f "
                 "(%.1f%% of input cost)" % (recoverable, pct * 100.0))
    lines.append("Cache reads: %d tokens as logged, %d canonical"
                 % (sim_logged.read_tokens, sim_canonical.read_tokens))
    return "\n".join(lines) + "\n"


def format_evaluation_summary(results):
    """The shipped evaluation summary (results/evaluation_summary.md)."""
    det = results["detection"]
    est = results["estimator"]
    lines = []
    lines.append("# Evaluation summary")
    lines.append("")
    lines.append("%d seeded traces (%d requests each, %d consecutive "
                 "pairs), planted ground truth throughout. Pricing: "
                 "read %.2f / write %.2f / base %.2f per token; TTL "
                 "%.1f min."
                 % (results["n_traces"],
                    results["n_requests_per_trace"],
                    results["n_pairs"],
                    results["pricing"]["read_rate"],
                    results["pricing"]["write_rate"],
                    results["pricing"]["base_rate"],
                    results["ttl_minutes"]))
    lines.append("")
    lines.append("## Recovery by scenario family")
    lines.append("")
    lines.append("| family | logged cost | canonical cost | "
                 "recoverable |")
    lines.append("|---|---|---|---|")
    for family, fam in results["families"].items():
        lines.append("| %s | %.1f | %.1f | %.1f%% |" % (
            family, fam["logged_cost"], fam["canonical_cost"],
            fam["recoverable_pct"] * 100.0))
    lines.append("")
    lines.append("Pooled recoverable share of input cost: **%.1f%%**."
                 % (results["pooled_recoverable_pct"] * 100.0))
    lines.append("")
    lines.append("## Breaker detection (first-divergence classifier)")
    lines.append("")
    lines.append("Overall: precision **%.3f**, recall **%.3f**, "
                 "F1 **%.3f** (tp %d, fp %d, fn %d)."
                 % (det["precision"], det["recall"], det["f1"],
                    det["tp"], det["fp"], det["fn"]))
    lines.append("")
    lines.append("| class | precision | recall | tp | fp | fn |")
    lines.append("|---|---|---|---|---|---|")
    for cls in BREAKER_CLASSES:
        entry = det["per_class"][cls]
        lines.append("| %s | %.3f | %.3f | %d | %d | %d |" % (
            cls, entry["precision"], entry["recall"],
            entry["tp"], entry["fp"], entry["fn"]))
    lines.append("")
    lines.append("Flagged breakers masked behind an earlier "
                 "divergence: %d." % results["masked_breakers"])
    lines.append("")
    lines.append("## Estimator accuracy (vs the cache model)")
    lines.append("")
    lines.append("| estimator | lost-token MAE | lost-token rel err | "
                 "recoverable-cost rel err |")
    lines.append("|---|---|---|---|")
    for name in ("audit", "baseline"):
        entry = est[name]
        lines.append("| %s | %.1f | %.3f | %.3f |" % (
            name, entry["lost_token_mae"], entry["lost_token_rel_err"],
            entry["recoverable_rel_err"]))
    lines.append("")
    lines.append("## Where the lost tokens belong (planted class)")
    lines.append("")
    lines.append("| planted primary | share of lost tokens |")
    lines.append("|---|---|")
    for key, share in results["attribution_shares"].items():
        lines.append("| %s | %.1f%% |" % (key, share * 100.0))
    lines.append("")
    return "\n".join(lines)
