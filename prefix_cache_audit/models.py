"""Data model: segments, requests, traces, and the declared pricing.

A *trace* is one agent session: a sequence of requests. Each request
is an ordered list of *segments* -- the building blocks a real agent
prompt is assembled from (header, system text, tool definitions, a
JSON state blob, retrieved chunks, conversation history, a volatile
scratchpad, the current user turn). A segment carries two texts:

- ``text`` -- what was actually logged, cache hazards included;
- ``canonical_text`` -- what the segment looks like under best
  practice (volatile header fields frozen, tool definitions sorted,
  JSON keys sorted, history appended rather than rewritten).

The gap between the two is the audit's subject. A segment may also
carry a ``breaker`` label: the planted ground-truth class of the
cache hazard its logged form embodies. The auditor never reads the
label; the evaluation scores the auditor against it.

Tokens are whitespace-delimited words -- a declared, deterministic
approximation used consistently by the generator, the auditor and
the cache model, so every comparison in this project is internal.
"""

from dataclasses import dataclass, field

# Cache geometry and pricing conventions (declared, Anthropic-like):
# full blocks of BLOCK_TOKENS are cached; a cache read costs
# READ_RATE per token, writing a fresh block costs WRITE_RATE, and
# the uncacheable partial tail block costs BASE_RATE.
BLOCK_TOKENS = 16
DEFAULT_TTL_MINUTES = 5.0

BREAKER_CLASSES = (
    "header_volatile",
    "tool_order_shuffle",
    "json_key_reorder",
    "history_rewrite",
    "retrieved_before_static",
)

STATIC_KINDS = ("system", "tools")

# Canonical segment order: stable content first, volatile content
# last, so the shared prefix is as long as physics allows.
CANONICAL_RANK = {
    "header": 0,
    "system": 1,
    "tools": 2,
    "json_blob": 3,
    "history": 4,
    "retrieved": 5,
    "volatile": 6,
    "user": 7,
}

# Header fields whose values change per request by design.
VOLATILE_HEADER_KEYS = ("ts", "request", "nonce", "trace")


def tokenize(text):
    """Split text into tokens (whitespace-delimited words)."""
    return text.split()


def block_floor(n_tokens, block_tokens=BLOCK_TOKENS):
    """Largest multiple of the block size not exceeding n_tokens."""
    return (n_tokens // block_tokens) * block_tokens


@dataclass(frozen=True)
class Pricing:
    """Per-token prices in cost units (per 1M tokens, read as USD)."""

    read_rate: float = 0.30
    write_rate: float = 3.75
    base_rate: float = 3.00


DEFAULT_PRICING = Pricing()


@dataclass
class Segment:
    seg_id: str
    kind: str
    text: str
    canonical_text: str = None
    breaker: str = None

    def __post_init__(self):
        if self.canonical_text is None:
            self.canonical_text = self.text

    @property
    def tokens(self):
        return tokenize(self.text)

    @property
    def token_count(self):
        return len(self.tokens)

    def to_dict(self):
        return {
            "seg_id": self.seg_id,
            "kind": self.kind,
            "text": self.text,
            "canonical_text": self.canonical_text,
            "breaker": self.breaker,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            seg_id=data["seg_id"],
            kind=data["kind"],
            text=data["text"],
            canonical_text=data.get("canonical_text"),
            breaker=data.get("breaker"),
        )


@dataclass
class Request:
    index: int
    at_minutes: float
    segments: list = field(default_factory=list)

    def token_stream(self):
        """The request's full token stream, in logged segment order."""
        stream = []
        for segment in self.segments:
            stream.extend(segment.tokens)
        return stream

    @property
    def total_tokens(self):
        return sum(segment.token_count for segment in self.segments)

    def segment_by_id(self, seg_id):
        for segment in self.segments:
            if segment.seg_id == seg_id:
                return segment
        return None

    def segment_at_token(self, token_index):
        """The segment whose token span contains token_index."""
        offset = 0
        for segment in self.segments:
            if token_index < offset + segment.token_count:
                return segment
            offset += segment.token_count
        return None

    def to_dict(self):
        return {
            "index": self.index,
            "at_minutes": self.at_minutes,
            "segments": [segment.to_dict() for segment in self.segments],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            index=data["index"],
            at_minutes=data["at_minutes"],
            segments=[Segment.from_dict(s) for s in data["segments"]],
        )


@dataclass
class Trace:
    family: str
    seed: int
    requests: list = field(default_factory=list)

    @property
    def trace_id(self):
        return "%s-%d" % (self.family, self.seed)

    def to_dict(self):
        return {
            "family": self.family,
            "seed": self.seed,
            "requests": [request.to_dict() for request in self.requests],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            family=data["family"],
            seed=data["seed"],
            requests=[Request.from_dict(r) for r in data["requests"]],
        )
