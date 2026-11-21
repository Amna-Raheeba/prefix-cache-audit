# Changelog

## 0.1.0 — 2026-11-22

- Initial release.
- Seeded trace generator with eight scenario families (stable
  control, header clock, tool shuffle, JSON churn with genuine
  value-change decoys, history rewrite, retrieved first, mixed
  kitchen sink, long-gap TTL), each request assembled from typed
  segments with a canonical form and planted breaker ground truth.
- Reference cache model: chained-hash block prefix cache (16-token
  blocks) with a sliding TTL, priced at declared read / write /
  base rates.
- First-divergence auditor: token-level LCP per consecutive pair,
  block-rounded lost-token estimates, and shape-based breaker
  classification (volatile header fields, tool-order shuffle, JSON
  key reorder, history rewrite, retrieved-before-static), with
  masked-breaker reporting and a segment-granularity baseline
  estimator.
- Canonicaliser: volatile header fields frozen, tools sorted, JSON
  keys sorted, history appended, segments re-ordered
  stable-before-volatile.
- Seeded evaluation over 48 traces: canonical ordering recovers
  49.9% of input cost pooled (0.0% for the control and the
  TTL-bound family), breaker detection P 1.000 / R 0.999, LCP
  estimator lost-token relative error 0.018 vs 0.373 for the
  segment baseline.
- Streamlit dashboard (Audit / Replay / Evaluation), CLI demo and
  evaluate commands, runnable notebook scripts, and a
  headline-drift reproduction guard.
