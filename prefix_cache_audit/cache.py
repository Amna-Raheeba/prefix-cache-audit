"""The reference cache model: a block prefix cache with a TTL.

The prompt is a flat token stream. It is cut into full blocks of
``block_tokens``; each block is identified by a hash chained from
its predecessor's hash, so a block is only ever reusable as part of
the exact prefix that produced it -- the defining property of
prefix caching. A request reuses the longest prefix of blocks that
are present and unexpired; the first miss ends reuse, and every
later block is computed fresh and stored. The trailing partial
block is computed but never stored.

Expiry is a sliding TTL: a hit refreshes the block's expiry to
``now + ttl``. The cache is unbounded (no eviction pressure), which
is declared here and in the README: this model prices divergence
and expiry, not capacity.

Costs follow the declared ``Pricing``: read tokens at the read
rate, freshly written block tokens at the write rate, the partial
tail at the base rate.
"""

import hashlib
from dataclasses import dataclass, field

from .models import BLOCK_TOKENS, DEFAULT_PRICING, DEFAULT_TTL_MINUTES


@dataclass
class RequestUsage:
    index: int
    read_tokens: int = 0
    write_tokens: int = 0
    base_tokens: int = 0
    cost: float = 0.0

    @property
    def lost_tokens(self):
        """Tokens not served from cache: writes plus the tail."""
        return self.write_tokens + self.base_tokens


@dataclass
class SimResult:
    per_request: list = field(default_factory=list)
    total_cost: float = 0.0
    read_tokens: int = 0
    write_tokens: int = 0
    base_tokens: int = 0

    @property
    def lost_tokens(self):
        return self.write_tokens + self.base_tokens


def _block_hash(prev_hash, block_tokens):
    payload = prev_hash + "|" + " ".join(block_tokens)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CacheSimulator:
    def __init__(self, pricing=DEFAULT_PRICING,
                 ttl_minutes=DEFAULT_TTL_MINUTES,
                 block_tokens=BLOCK_TOKENS):
        self.pricing = pricing
        self.ttl_minutes = ttl_minutes
        self.block_tokens = block_tokens

    def simulate(self, requests):
        """Replay a request sequence through the cache."""
        cache = {}
        result = SimResult()
        size = self.block_tokens
        for request in requests:
            tokens = request.token_stream()
            n_blocks = len(tokens) // size
            usage = RequestUsage(index=request.index)
            prev_hash = ""
            missed = False
            for b in range(n_blocks):
                block = tokens[b * size:(b + 1) * size]
                digest = _block_hash(prev_hash, block)
                expiry = cache.get(digest)
                if (not missed and expiry is not None
                        and expiry >= request.at_minutes):
                    usage.read_tokens += size
                else:
                    missed = True
                    usage.write_tokens += size
                cache[digest] = request.at_minutes + self.ttl_minutes
                prev_hash = digest
            usage.base_tokens = len(tokens) - n_blocks * size
            usage.cost = (
                usage.read_tokens * self.pricing.read_rate
                + usage.write_tokens * self.pricing.write_rate
                + usage.base_tokens * self.pricing.base_rate)
            result.per_request.append(usage)
            result.total_cost += usage.cost
            result.read_tokens += usage.read_tokens
            result.write_tokens += usage.write_tokens
            result.base_tokens += usage.base_tokens
        return result
