# Prefix Cache Audit

## 1. What it is

Prefix caching is the largest silent line item in an agent's
inference bill: when consecutive requests share a prompt prefix,
the shared part is served from cache at a tenth of the price, and
everything after the first changed token is computed -- and paid
for -- again. Real agent prompts break their own prefixes in
boringly specific ways. A timestamp in the header changes on every
request. The tool list is serialised in whatever order the
framework felt like. A JSON state blob is re-dumped with its keys
in a new order. The history is re-summarised instead of appended.
Retrieved chunks are parked *in front of* the system text, so their
churn invalidates the static segments behind them.

Each of these is a one-line fix -- once you know it is happening,
where, and what it costs. In a production log, nobody knows: the
bill just looks like the cost of doing business.

This project is an offline audit instrument for that question. It
reads a request trace, computes the **first-divergence point** of
every consecutive pair, attributes the lost cache tokens to the
**segment class responsible** for the divergence, and then replays
the trace under a **canonical stable ordering** through a declared
cache model to price what the fixes would recover. Everything is
deterministic and seeded: the traces are synthetic sessions with
planted cache breakers, so the instrument itself is scored --
detection precision/recall, estimation error, recovered cost --
instead of merely demonstrated.

## 2. The novel mechanism

Four pieces, none of them a trained model:

1. **First-divergence attribution.** For each consecutive pair of
   requests, the token-level longest common prefix locates the
   exact token where reuse dies. The segment containing that token
   is classified by *shape*: a header whose volatile fields explain
   the difference, a tool list whose entries are the same multiset
   re-ordered, a JSON blob that parses to the same object, a
   history that is not an extension of its predecessor, a retrieved
   segment sitting in front of static content. The output is not
   "your cache hit rate is low" but "this segment class, at this
   position, costs you these tokens".
2. **A reference cache model.** A block prefix cache (16-token
   blocks, hashes chained from the predecessor block, sliding
   5-minute TTL, declared read/write/base prices) replays the
   trace as logged. Lost tokens per request are measured, not
   asserted -- and attributed to the planted primary breaker of
   each pair.
3. **Counterfactual canonical replay.** Every segment also carries
   a canonical form (volatile header fields frozen, tools sorted
   by name, JSON keys sorted, history appended verbatim) and the
   segments are re-ordered stable-before-volatile. Replaying the
   canonical trace through the same cache model prices the
   recovery. Canonicalisation cannot fix genuine churn -- new
   retrieval, a new user question, a state blob whose *values*
   changed -- it moves the churn behind the static prefix, where
   it costs its own tokens and no one else's.
4. **Masked-breaker reporting.** A divergence at token 3 hides
   every hazard behind it. The audit counts the planted breakers
   that changed *behind* the first divergence of each pair -- the
   fixes you cannot even see until the earliest breaker is fixed.
   In the mixed traces, that is 413 hazards across 48 traces,
   invisible to any per-pair analysis that stops at the first
   divergence and says nothing about the rest.

## 3. Prior art and the differentiator

- **"Prefix Sharing Is a Sorting Problem"** proves the optimal
  chunk ordering for a *serving stack* that is free to choose
  layouts. It optimises; it does not diagnose an existing agent's
  traces or attribute loss to the segment that caused it.
- **Provider documentation and practitioner playbooks** list the
  anti-patterns anecdotally -- "don't put timestamps in your
  system prompt" -- without measuring which one a given system
  actually commits, or what it costs there.
- **Cache observability in serving stacks** reports aggregate hit
  rates. A hit rate says *that* reuse failed; it cannot say which
  segment broke the prefix, whether the breakage was avoidable
  ordering or genuine churn, or what a fix is worth.

The differentiator: an offline diagnostic that attributes cache
loss in an existing trace to specific segment classes by
first-divergence analysis, separates avoidable breakage from
genuine churn and from TTL expiry, and prices the recovery with a
counterfactual replay -- validated against planted ground truth.

## 4. How the audit works

1. **Generate** a session from one of eight scenario families
   (`stable`, `header_clock`, `tool_shuffle`, `json_churn`,
   `history_rewrite`, `retrieved_first`, `mixed_kitchen_sink`,
   `long_gap_ttl`), each assembling requests from typed segments
   (header, system, tools, JSON blob, history, retrieved,
   volatile, user) the way real prompts go right or wrong.
2. **Diverge**: per consecutive pair, compute the token LCP; the
   estimated lost tokens are the request's tokens beyond the
   block-rounded LCP, and the diverging segment is classified by
   the rules in section 2. A JSON blob whose values genuinely
   changed is *not* called a key reorder; a history that merely
   grew is *not* called a rewrite.
3. **Replay** the trace, as logged and canonicalised, through the
   reference cache model under declared pricing (read 0.30, write
   3.75, base 3.00 per token; 16-token blocks; 5-minute TTL).
4. **Score** (in the evaluation harness) the classifier against
   the planted primary breaker of each pair, and the LCP estimator
   against the cache model's measured lost tokens, alongside a
   segment-granularity baseline estimator (any changed segment
   wastes all its tokens -- the heuristic this tool replaces).

## 5. Measured results

48 seeded traces (8 families x 6 seeds), 24 requests each, 1,104
consecutive pairs, planted ground truth throughout. Full tables in
`results/evaluation_summary.md`; regeneration guarded by
`scripts/reproduce_results.py`.

**Recovery by canonical ordering (share of as-logged input cost):**

| family | recoverable |
|---|---|
| mixed_kitchen_sink | 69.1% |
| header_clock | 68.4% |
| retrieved_first | 68.4% |
| tool_shuffle | 63.9% |
| history_rewrite | 57.6% |
| json_churn | 38.5% |
| stable (control) | 0.0% |
| long_gap_ttl | 0.0% |
| **pooled** | **49.9%** |

- **The two zeros are the audit's honesty check.** The control
  trace is assembled in canonical order with stable segments, and
  the audit recovers exactly 0.0% from it -- it does not invent
  savings in a well-built prompt. The long-gap family has a real
  breaker (a shuffled tool list), but requests land 6-12 minutes
  apart against a 5-minute TTL, so every block expires before it
  can be reused and reordering recovers 0.0%: expiry, not ordering,
  is the binding cost, and the audit says so.
- **The earliest segments own the loss.** Of all lost tokens,
  30.7% belong to pairs whose primary breaker is the volatile
  header and 28.1% to the shuffled tool list -- two segment
  classes at the front of the prompt account for nearly
  three-fifths of the waste, because everything behind a broken
  prefix is recomputed with it.
- **JSON churn is capped by genuine change.** Key reordering is
  fully recoverable, but the blob's values genuinely change on
  ~30% of requests, and each genuine change -- sitting early, at
  canonical rank 3 -- still invalidates the history and retrieval
  behind it. 38.5% is what ordering alone can buy; the rest needs
  the state moved late or out of the prompt.
- **Detection: precision 1.000, recall 0.999, F1 0.999** (922 tp,
  0 fp, 1 fn over 1,104 pairs; per-class recall 1.000 except
  history rewrite at 0.993). The single miss is a one-turn history
  whose rewording coincided word-for-word with the previous
  request's rewording of the same turn -- from the log alone it is
  indistinguishable from an append, because it is one.
- **The LCP estimator tracks the cache model; the baseline does
  not.** Lost-token relative error: audit **0.018** (MAE 201
  tokens per trace) vs segment-granularity baseline **0.373**
  (MAE 2,034). Recoverable-cost relative error: **0.127** vs
  **0.814**. The baseline fails in both directions -- it counts a
  grown history segment's every token as waste, and counts a
  7-token volatile header as 7 wasted tokens when it actually
  wastes the whole request.
- **The estimator's known blind spot is expiry.** In the long-gap
  family it estimates 59,939 lost tokens against the cache model's
  68,931: it assumes the previous request's prefix is still
  cached, and cannot see evictions. That gap is the measured price
  of auditing from logs without a cache model.

## 6. The demo trace

The shipped demo (`examples/sample_report.md`, real captured
output) is a mixed kitchen-sink session: a volatile header in
front of retrieved-first layout and a shuffled tool list. The
header breaks every pair at token 3, so as logged the session
scores **zero cache reads**; canonical ordering recovers **59.6%**
of its input cost -- and the report still lists 33 further planted
breakers masked behind the header in just 11 pairs, which only
become visible, and payable, once the header is fixed.

## 7. Honest limits

- **The traces are synthetic and the cache is a model.** Real
  serving stacks differ in block size, eviction policy, routing
  (a prefix cached on one replica may not exist on another), and
  pricing; the numbers here are properties of the declared model
  (16-token blocks, sliding TTL, unbounded cache) applied to
  seeded traces, not measurements of any production system. The
  instrument -- divergence attribution, canonical replay, masking
  counts -- is what transfers; the percentages are the testbed's.
- **Detection is near-exact partly because the testbed is
  separable.** Planted breakers produce unambiguous shapes (a
  reordered tool list is exactly a multiset permutation). Real
  logs add messier hazards -- whitespace drift, Unicode
  normalisation, template re-rendering -- that a shape classifier
  would need more rules, and would sometimes get wrong. The one
  measured miss (section 5) is the shape of real failure: a
  breaker whose logged effect is identical to benign behaviour.
- **The classifier sees consecutive pairs only.** A segment that
  changes every *other* request (A/B template rotation) breaks
  reuse just as surely but presents as two alternating stable
  prefixes; per-pair first-divergence analysis attributes each
  pair correctly yet understates the pattern. Cross-request
  prefix mining is the stated next step.
- **Tokens are whitespace words.** Real tokenisers shift block
  boundaries by a few tokens; every comparison in the evaluation
  uses the same tokenisation on both sides, so the *relative*
  results stand, but absolute token counts would move slightly
  under a BPE tokeniser.
- **Canonicalisation is a counterfactual, not a patch.** Freezing
  a header timestamp assumes the application does not need it in
  the prompt (it usually does not -- it needs it in the request
  metadata). The audit prices the fix; whether the fix is
  available is an engineering judgement it cannot make.

## 8. Running it

```bash
pip install -r requirements.txt        # pytest + streamlit only
python -m prefix_cache_audit demo      # audit one mixed trace
python -m prefix_cache_audit demo --family header_clock --seed 3
python -m prefix_cache_audit evaluate --out results
python scripts/reproduce_results.py    # headline-drift guard
python examples/run_audit.py           # audit the shipped demo trace
python notebooks/01_demo_run.py
python notebooks/02_evaluation_experiment.py
streamlit run app.py                   # dashboard: Audit / Replay / Evaluation
pytest -q
```

## 9. Repository layout

```
prefix_cache_audit/   models, generate, cache, canonical, audit,
                      evaluate, report, cli
data/                 demo_trace.json (planted ground truth),
                      scenarios.json
results/              evaluation.json / .csv, evaluation_summary.md,
                      HEADLINE.md
notebooks/            01_demo_run.py, 02_evaluation_experiment.py
examples/             run_audit.py, sample_report.md
scripts/              build_cases.py, reproduce_results.py
tests/                pytest suite (70+ tests)
app.py                Streamlit dashboard
```

## 10. License

MIT (see `LICENSE`). Author: Amna Raheeba.
