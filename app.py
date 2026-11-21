"""Streamlit dashboard for prefix-cache-audit.

Three tabs:
1. Audit -- pick a scenario family and seed; the trace is generated
   and audited live, with the per-request divergence table and the
   attributed breaker classes.
2. Replay -- the same trace replayed through the cache model as
   logged and canonicalised: per-request cost, totals, and the
   recoverable share.
3. Evaluation -- the shipped aggregate results from
   results/evaluation.json: recovery per family, breaker detection,
   and estimator accuracy.

Run:  streamlit run app.py
"""

import io
import json
import os

import pandas as pd
import streamlit as st

from prefix_cache_audit.audit import analyze_trace
from prefix_cache_audit.cache import CacheSimulator
from prefix_cache_audit.canonical import canonicalize_trace
from prefix_cache_audit.generate import SCENARIOS, build_trace

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_results():
    path = os.path.join(HERE, "results", "evaluation.json")
    if not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _pair_rows(trace, audit):
    rows = []
    for pair in audit.pairs:
        rows.append({
            "request": pair.index,
            "at (min)": trace.requests[pair.index].at_minutes,
            "lcp tokens": pair.lcp_tokens,
            "lost (est)": pair.lost_tokens_est,
            "diverging": pair.diverging_kind or "-",
            "predicted": pair.predicted_class or "-",
            "planted": pair.planted_class or "-",
        })
    return rows


def main():
    st.set_page_config(page_title="Prefix Cache Audit")
    st.title("Prefix Cache Audit")

    family = st.selectbox("Scenario family", list(SCENARIOS))
    seed = st.number_input("Seed", min_value=0, max_value=99, value=3)
    trace = build_trace(family, int(seed), 24)
    audit = analyze_trace(trace)
    simulator = CacheSimulator()
    sim_logged = simulator.simulate(trace.requests)
    sim_canonical = simulator.simulate(
        canonicalize_trace(trace).requests)

    tab_audit, tab_replay, tab_eval = st.tabs(
        ["Audit", "Replay", "Evaluation"])

    with tab_audit:
        st.subheader("First-divergence audit: %s" % trace.trace_id)
        st.write(SCENARIOS[family])
        st.dataframe(pd.DataFrame(_pair_rows(trace, audit)),
                     use_container_width=True)
        st.write("Estimated lost tokens: **%d** "
                 "(segment-granularity baseline: %d); flagged "
                 "breakers masked behind an earlier divergence: %d"
                 % (audit.est_wasted_tokens,
                    audit.baseline_wasted_tokens,
                    audit.masked_count))
        if audit.class_counts:
            counts = pd.DataFrame(
                [{"class": cls, "pairs": n}
                 for cls, n in sorted(audit.class_counts.items())])
            st.bar_chart(counts.set_index("class"))

    with tab_replay:
        st.subheader("Cache replay: as logged vs canonical")
        rows = []
        for logged, canonical in zip(sim_logged.per_request,
                                     sim_canonical.per_request):
            rows.append({"request": logged.index,
                         "as logged": logged.cost,
                         "canonical": canonical.cost})
        st.bar_chart(pd.DataFrame(rows).set_index("request"))
        recoverable = sim_logged.total_cost - sim_canonical.total_cost
        pct = (recoverable / sim_logged.total_cost
               if sim_logged.total_cost else 0.0)
        st.write("As-logged cost **%.1f**; canonical cost **%.1f**; "
                 "recoverable **%.1f (%.1f%%)**"
                 % (sim_logged.total_cost, sim_canonical.total_cost,
                    recoverable, pct * 100.0))
        st.write("Cache reads: %d tokens as logged, %d canonical."
                 % (sim_logged.read_tokens, sim_canonical.read_tokens))

    with tab_eval:
        st.subheader("Shipped evaluation (48 seeded traces)")
        results = _load_results()
        if results is None:
            st.write("results/evaluation.json not found; run "
                     "`python -m prefix_cache_audit evaluate`.")
        else:
            fam_rows = [{
                "family": name,
                "recoverable %": round(
                    fam["recoverable_pct"] * 100.0, 1),
                "logged cost": round(fam["logged_cost"], 1),
                "canonical cost": round(fam["canonical_cost"], 1),
            } for name, fam in results["families"].items()]
            st.dataframe(pd.DataFrame(fam_rows),
                         use_container_width=True)
            det = results["detection"]
            st.write("Breaker detection: precision **%.3f**, "
                     "recall **%.3f**, F1 **%.3f**"
                     % (det["precision"], det["recall"], det["f1"]))
            est = results["estimator"]
            st.write("Lost-token relative error: audit **%.3f** "
                     "vs segment baseline **%.3f**"
                     % (est["audit"]["lost_token_rel_err"],
                        est["baseline"]["lost_token_rel_err"]))
            st.write("Pooled recoverable share of input cost: "
                     "**%.1f%%**"
                     % (results["pooled_recoverable_pct"] * 100.0))


if __name__ == "__main__":
    main()
