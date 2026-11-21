"""Tests for the reference cache model."""

from prefix_cache_audit.cache import CacheSimulator
from prefix_cache_audit.models import Pricing, Request, Segment

BLOCK = 16


def _req(index, at, tokens):
    return Request(index=index, at_minutes=at,
                   segments=[Segment("s", "system", " ".join(tokens))])


def _tokens(n, prefix="t"):
    return ["%s%02d" % (prefix, i) for i in range(n)]


def test_first_request_is_all_writes_plus_tail():
    sim = CacheSimulator()
    result = sim.simulate([_req(0, 0.0, _tokens(40))])
    usage = result.per_request[0]
    assert usage.read_tokens == 0
    assert usage.write_tokens == 32
    assert usage.base_tokens == 8


def test_identical_second_request_reads_all_blocks():
    sim = CacheSimulator()
    result = sim.simulate([_req(0, 0.0, _tokens(40)),
                           _req(1, 1.0, _tokens(40))])
    usage = result.per_request[1]
    assert usage.read_tokens == 32
    assert usage.write_tokens == 0
    assert usage.base_tokens == 8


def test_early_divergence_loses_everything():
    sim = CacheSimulator()
    first = _tokens(48)
    second = ["changed"] + first[1:]
    result = sim.simulate([_req(0, 0.0, first), _req(1, 1.0, second)])
    assert result.per_request[1].read_tokens == 0
    assert result.per_request[1].write_tokens == 48


def test_late_divergence_keeps_early_blocks():
    sim = CacheSimulator()
    first = _tokens(48)
    second = first[:32] + ["x%02d" % i for i in range(16)]
    result = sim.simulate([_req(0, 0.0, first), _req(1, 1.0, second)])
    usage = result.per_request[1]
    assert usage.read_tokens == 32
    assert usage.write_tokens == 16


def test_same_block_content_after_different_prefix_misses():
    sim = CacheSimulator()
    shared_tail = _tokens(16, "s")
    first = _tokens(16, "a") + shared_tail
    second = _tokens(16, "b") + shared_tail
    result = sim.simulate([_req(0, 0.0, first), _req(1, 1.0, second)])
    assert result.per_request[1].read_tokens == 0


def test_ttl_expiry_forces_rewrite():
    sim = CacheSimulator(ttl_minutes=5.0)
    result = sim.simulate([_req(0, 0.0, _tokens(32)),
                           _req(1, 6.0, _tokens(32))])
    assert result.per_request[1].read_tokens == 0
    assert result.per_request[1].write_tokens == 32


def test_sliding_ttl_refresh_extends_life():
    sim = CacheSimulator(ttl_minutes=5.0)
    requests = [_req(0, 0.0, _tokens(32)), _req(1, 4.0, _tokens(32)),
                _req(2, 8.0, _tokens(32)), _req(3, 14.0, _tokens(32))]
    result = sim.simulate(requests)
    assert result.per_request[1].read_tokens == 32
    assert result.per_request[2].read_tokens == 32
    assert result.per_request[3].read_tokens == 0


def test_cost_arithmetic_matches_pricing():
    pricing = Pricing(read_rate=0.5, write_rate=2.0, base_rate=1.0)
    sim = CacheSimulator(pricing=pricing)
    result = sim.simulate([_req(0, 0.0, _tokens(40)),
                           _req(1, 1.0, _tokens(40))])
    first, second = result.per_request
    assert first.cost == 32 * 2.0 + 8 * 1.0
    assert second.cost == 32 * 0.5 + 8 * 1.0
    assert result.total_cost == first.cost + second.cost
    assert result.read_tokens == 32
    assert result.write_tokens == 32
    assert result.base_tokens == 16


def test_partial_tail_is_never_cached():
    sim = CacheSimulator()
    tokens = _tokens(20)
    result = sim.simulate([_req(0, 0.0, tokens), _req(1, 1.0, tokens),
                           _req(2, 2.0, tokens)])
    for usage in result.per_request:
        assert usage.base_tokens == 4
    assert result.per_request[2].read_tokens == 16


def test_append_only_growth_reuses_prefix():
    sim = CacheSimulator()
    first = _tokens(32)
    second = first + _tokens(16, "n")
    result = sim.simulate([_req(0, 0.0, first), _req(1, 1.0, second)])
    usage = result.per_request[1]
    assert usage.read_tokens == 32
    assert usage.write_tokens == 16
