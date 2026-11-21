"""Canonicalisation: the counterfactual best-practice prompt.

Each segment is replaced by its canonical text -- volatile header
fields frozen, tool definitions sorted by name, JSON keys sorted,
history in its appended (unrewritten) form -- and the segments are
re-ordered by ``CANONICAL_RANK``: stable content first, volatile
content last. The sort is stable, so segments of the same kind keep
their relative order.

Canonicalisation cannot fix genuine churn: retrieved chunks still
carry new content, the scratchpad still changes, the user still
asks a new question. It moves that churn behind the static prefix,
where it costs its own tokens and no one else's.
"""

from .models import CANONICAL_RANK, Request, Segment


def canonicalize_request(request):
    segments = []
    for segment in request.segments:
        segments.append(Segment(
            seg_id=segment.seg_id,
            kind=segment.kind,
            text=segment.canonical_text,
            canonical_text=segment.canonical_text,
            breaker=None,
        ))
    segments.sort(key=lambda seg: CANONICAL_RANK[seg.kind])
    return Request(index=request.index,
                   at_minutes=request.at_minutes,
                   segments=segments)


def canonicalize_trace(trace):
    from .models import Trace
    return Trace(
        family=trace.family,
        seed=trace.seed,
        requests=[canonicalize_request(r) for r in trace.requests],
    )
