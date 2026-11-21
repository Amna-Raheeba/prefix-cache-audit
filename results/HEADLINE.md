# Headline results

Across 48 seeded traces (8 scenario families x 6 seeds, 24 requests
each, 1,104 consecutive pairs), planted ground truth:

- **Canonical ordering recovers 49.9% of input-token cost pooled
  across families** -- and the recovery is exactly **0.0%** in the
  two families where it should be: the well-built control trace,
  and the long-gap family where a 5-minute cache TTL expires before
  requests 6-12 minutes apart can reuse anything, however ordered.
- Per family: volatile header **68.4%**, retrieved-before-static
  **68.4%**, mixed kitchen sink **69.1%**, shuffled tool list
  **63.9%**, rewritten history **57.6%**, JSON key churn **38.5%**
  (capped by the blob's genuine value changes, which no ordering
  can fix).
- Breaker detection by first-divergence classification: precision
  **1.000**, recall **0.999**, F1 **0.999** (922 tp, 0 fp, 1 fn).
  The single miss is a one-turn history whose rewording coincided
  word-for-word with the previous request's rewording --
  indistinguishable from an append in the log alone.
- Lost-token estimation: the token-level LCP estimator's relative
  error is **0.018** vs **0.373** for the segment-granularity
  heuristic; its known blind spot is TTL expiry (in the long-gap
  family it estimates 59,939 lost tokens against the cache model's
  68,931, because it cannot see evictions).
- **413** planted breakers were masked behind an earlier divergence
  -- hazards a pair analysis cannot see until the earliest breaker
  is fixed. The header alone accounts for **30.7%** of all lost
  tokens, the shuffled tool list for **28.1%**.

All numbers are measured on synthetic seeded traces under the
declared pricing and cache model; see README section 7 for limits.
