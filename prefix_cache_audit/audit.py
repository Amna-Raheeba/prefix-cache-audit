"""The audit instrument: first-divergence attribution.

For each consecutive pair of requests the auditor computes the
token-level longest common prefix (LCP). Everything from the first
divergent block onward must be recomputed, so the pair's estimated
lost tokens are the request's tokens beyond the block-rounded LCP.
The segment containing the divergence point is then classified by
*shape*, never by any planted label:

- a header whose volatile fields explain the difference ->
  ``header_volatile``;
- a tool segment whose tool entries are the same multiset in a
  different order -> ``tool_order_shuffle``;
- a JSON segment that parses to the same object -> ``json_key_reorder``
  (a JSON segment that parses *differently* is a genuine change);
- a history segment that is not an extension of its predecessor ->
  ``history_rewrite`` (a pure append is not a breaker);
- a retrieved segment sitting in front of a static segment ->
  ``retrieved_before_static``;
- anything else -> a genuine content change, not a breaker.

The auditor also derives the planted primary breaker from the
trace's ground-truth flags -- the earliest segment, in logged
order, whose text changed and which carries a breaker flag -- so
the evaluation can score the classifier. Flagged segments that
changed *behind* the first divergence are reported as masked: real
hazards the pair analysis cannot see until the earlier breaker is
fixed.

Two estimators of wasted tokens are provided: this token-level LCP
estimator, and a segment-granularity baseline (any segment whose
text changed counts all of its tokens as wasted) -- the heuristic a
practitioner would reach for without a divergence analysis.
"""

import json
from dataclasses import dataclass, field

from .models import (BLOCK_TOKENS, STATIC_KINDS, VOLATILE_HEADER_KEYS,
                     block_floor, tokenize)


@dataclass
class PairDivergence:
    index: int
    lcp_tokens: int = 0
    lost_tokens_est: int = 0
    diverging_kind: str = None
    predicted_class: str = None
    planted_class: str = None
    masked_classes: list = field(default_factory=list)


@dataclass
class AuditResult:
    trace_id: str = ""
    pairs: list = field(default_factory=list)
    est_wasted_tokens: int = 0
    baseline_wasted_tokens: int = 0
    class_counts: dict = field(default_factory=dict)
    masked_count: int = 0


def lcp_length(tokens_a, tokens_b):
    """Length of the longest common prefix of two token lists."""
    n = 0
    for tok_a, tok_b in zip(tokens_a, tokens_b):
        if tok_a != tok_b:
            break
        n += 1
    return n


def _normalize_header(text):
    out = []
    for token in text.split():
        if "=" in token:
            key = token.split("=", 1)[0]
            if key in VOLATILE_HEADER_KEYS:
                out.append(key + "=*")
                continue
        out.append(token)
    return " ".join(out)


def _tool_entries(text):
    entries = []
    current = []
    for token in text.split():
        if token.startswith("tool:") and current:
            entries.append(" ".join(current))
            current = [token]
        else:
            current.append(token)
    if current:
        entries.append(" ".join(current))
    return entries


def _try_parse_json(text):
    try:
        return json.loads(text), True
    except ValueError:
        return None, False


def classify_pair(prev_request, request, diverging_segment):
    """Classify the divergence by the diverging segment's shape.

    Returns a breaker class, or None for a genuine content change.
    """
    if diverging_segment is None:
        return None
    prev_segment = prev_request.segment_by_id(diverging_segment.seg_id)
    if prev_segment is None:
        return None
    kind = diverging_segment.kind

    if kind == "header":
        if (_normalize_header(diverging_segment.text)
                == _normalize_header(prev_segment.text)):
            return "header_volatile"
        return None

    if kind == "tools":
        entries = _tool_entries(diverging_segment.text)
        prev_entries = _tool_entries(prev_segment.text)
        if entries != prev_entries and sorted(entries) == sorted(prev_entries):
            return "tool_order_shuffle"
        return None

    if kind == "json_blob":
        parsed, ok = _try_parse_json(diverging_segment.text)
        prev_parsed, prev_ok = _try_parse_json(prev_segment.text)
        if ok and prev_ok:
            if parsed == prev_parsed:
                return "json_key_reorder"
            return None
        return None

    if kind == "history":
        prev_tokens = tokenize(prev_segment.text)
        tokens = tokenize(diverging_segment.text)
        if tokens[:len(prev_tokens)] == prev_tokens:
            return None  # pure append
        return "history_rewrite"

    if kind == "retrieved":
        seen = False
        for segment in request.segments:
            if segment.seg_id == diverging_segment.seg_id:
                seen = True
                continue
            if seen and segment.kind in STATIC_KINDS:
                return "retrieved_before_static"
        return None

    return None


def planted_primary(prev_request, request):
    """Ground truth: earliest changed, flagged segment in logged
    order, plus the flagged classes masked behind it."""
    primary = None
    masked = []
    seen_change = False
    for segment in request.segments:
        prev_segment = prev_request.segment_by_id(segment.seg_id)
        changed = (prev_segment is None
                   or prev_segment.text != segment.text)
        if not changed:
            continue
        if not seen_change:
            seen_change = True
            primary = segment.breaker
        elif segment.breaker is not None:
            masked.append(segment.breaker)
    return primary, masked


def analyze_trace(trace, block_tokens=BLOCK_TOKENS):
    """Run the divergence audit over one trace."""
    result = AuditResult(trace_id=trace.trace_id)
    requests = trace.requests
    for i in range(1, len(requests)):
        prev_request = requests[i - 1]
        request = requests[i]
        prev_tokens = prev_request.token_stream()
        tokens = request.token_stream()
        lcp = lcp_length(prev_tokens, tokens)
        lost_est = len(tokens) - block_floor(lcp, block_tokens)
        diverging = None
        if lcp < len(tokens):
            diverging = request.segment_at_token(lcp)
        predicted = classify_pair(prev_request, request, diverging)
        planted, masked = planted_primary(prev_request, request)
        result.pairs.append(PairDivergence(
            index=request.index,
            lcp_tokens=lcp,
            lost_tokens_est=lost_est,
            diverging_kind=diverging.kind if diverging else None,
            predicted_class=predicted,
            planted_class=planted,
            masked_classes=masked,
        ))
        result.est_wasted_tokens += lost_est
        if predicted is not None:
            result.class_counts[predicted] = (
                result.class_counts.get(predicted, 0) + 1)
        result.masked_count += len(masked)
    result.baseline_wasted_tokens = baseline_wasted_tokens(trace)
    return result


def baseline_wasted_tokens(trace):
    """Segment-granularity heuristic: a segment whose text changed
    at all wastes all of its tokens."""
    total = 0
    requests = trace.requests
    for i in range(1, len(requests)):
        prev_request = requests[i - 1]
        for segment in requests[i].segments:
            prev_segment = prev_request.segment_by_id(segment.seg_id)
            if prev_segment is None or prev_segment.text != segment.text:
                total += segment.token_count
    return total
