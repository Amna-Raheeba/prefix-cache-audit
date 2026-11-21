"""Seeded trace generator with planted cache breakers.

Each scenario family assembles a session of requests the way real
agent prompts go wrong -- or, for the control family, right. Every
segment knows its canonical form and, where its logged form embodies
a cache hazard, the planted breaker class. The generator derives
per-request flags from what it actually did (a JSON segment whose
values genuinely changed is *not* flagged as a key reorder), so the
ground truth the auditor is scored against is honest.

Families:

- ``stable`` -- the control: constant header, sorted tools,
  append-only history. Retrieval churns, as it should, *after* the
  static prefix.
- ``header_clock`` -- a request counter and timestamp ride in the
  header, at the very front of every prompt.
- ``tool_shuffle`` -- the tool list is re-shuffled every request.
- ``json_churn`` -- a JSON state blob is re-serialised with shuffled
  keys; on some requests its values genuinely change (decoys the
  auditor must not call reorders).
- ``history_rewrite`` -- history is re-worded every turn instead of
  appended; retrieval is held fixed so the rewrite is the first
  divergence.
- ``retrieved_first`` -- fresh retrieved chunks are placed *before*
  the system text and tool definitions.
- ``mixed_kitchen_sink`` -- volatile header, retrieved-first and a
  shuffled tool list in one trace; the header masks the rest.
- ``long_gap_ttl`` -- a shuffled tool list, but requests arrive
  6-12 minutes apart against a 5-minute cache TTL: the honest case
  where reordering cannot recover what expiry already took.
"""

import json
import random
import zlib

from .models import Request, Segment, Trace

SCENARIOS = {
    "stable": "Control session: constant header, sorted tools, "
              "append-only history; retrieval churns after the "
              "static prefix, where churn is cheap.",
    "header_clock": "A request counter and timestamp in the header "
                    "of every prompt; the prefix dies at token 3.",
    "tool_shuffle": "The tool definitions are re-shuffled on every "
                    "request; same tools, same text, new order.",
    "json_churn": "A JSON state blob re-serialised with shuffled "
                  "keys each request, with occasional genuine value "
                  "changes the auditor must not blame on ordering.",
    "history_rewrite": "Conversation history is re-worded every "
                       "turn (synonym drift) instead of appended "
                       "verbatim.",
    "retrieved_first": "Fresh retrieved chunks are placed before "
                       "the system text and tool definitions, so "
                       "their churn invalidates the static segments "
                       "behind them.",
    "mixed_kitchen_sink": "Volatile header, retrieved-first layout "
                          "and a shuffled tool list in one session; "
                          "the earliest breaker masks the others.",
    "long_gap_ttl": "Shuffled tool list, but requests land 6-12 "
                    "minutes apart against a 5-minute cache TTL; "
                    "expiry, not ordering, is the binding cost.",
}

HEADER_VOLATILE_FAMILIES = ("header_clock", "mixed_kitchen_sink")
TOOL_SHUFFLE_FAMILIES = ("tool_shuffle", "mixed_kitchen_sink",
                         "long_gap_ttl")
JSON_FAMILIES = ("json_churn", "mixed_kitchen_sink")
RETRIEVED_FIRST_FAMILIES = ("retrieved_first", "mixed_kitchen_sink")

SYSTEM_TEXT = (
    "you are the support agent for northwind retail answer every "
    "question with the verified order facts first be concise never "
    "invent a tracking number or a delivery date escalate billing "
    "disputes and legal threats to a human agent immediately cite "
    "the policy section whenever you quote a refund rule keep a "
    "calm professional tone and close every reply with the next "
    "step for the customer"
)

TOOL_CATALOGUE = (
    ("search_orders",
     "find orders by customer name date range or status filter"),
    ("get_tracking",
     "return the carrier tracking state for one order number"),
    ("issue_refund",
     "refund a payment method for a returned or damaged item"),
    ("update_address",
     "change the delivery address on an order not yet shipped"),
    ("check_inventory",
     "report warehouse stock levels for a product code"),
    ("send_email",
     "send a templated message to the customer on file"),
    ("create_ticket",
     "open a support ticket and return its reference code"),
    ("apply_discount",
     "apply a goodwill discount code to the current order"),
)

FRAGMENTS = (
    "policy section 4.2 states refunds for damaged items are issued "
    "within five business days",
    "the warehouse scan shows the parcel left the depot on the "
    "morning truck",
    "carrier notes say the delivery van serves this district after "
    "midday",
    "section 7.1 covers address changes made before the shipping "
    "label is printed",
    "the returns desk accepts items within thirty days of the "
    "delivery scan",
    "inventory for the winter catalogue refreshes every night at "
    "two",
    "section 2.9 explains how goodwill discounts stack with sale "
    "prices",
    "the customer file lists a preferred contact window in the "
    "evening",
    "gift orders hide prices on the packing slip by default rule",
    "section 5.4 describes exchanges for a different size or colour",
    "the depot log records a weather delay on the northern route",
    "loyalty points post three days after the payment clears",
)

QUESTIONS = (
    "where is my order and when will it arrive at my house",
    "the item arrived broken and i would like a refund please",
    "can i change the delivery address before it ships out",
    "do you have this jacket in a medium at the depot",
    "my discount code did not apply at the checkout page",
    "the tracking page has not moved for three days now",
    "i need a gift receipt without the price printed on it",
    "how many loyalty points did my last order earn me",
    "the wrong size arrived and i want to exchange it",
    "can someone call me back about the billing problem",
)

TURN_USER = (
    "user: my order status check shows the delivery is late again",
    "user: the refund for the broken item is still not visible",
    "user: please check whether the address change went through",
    "user: the delivery problem started right after the depot scan",
    "user: i asked for a size exchange but heard nothing back",
    "user: the order arrived damaged and the box was open",
)

TURN_AGENT = (
    "agent: i will check the order status and the delivery scan now",
    "agent: the refund was issued and should clear within five days",
    "agent: your address change is confirmed for the next delivery",
    "agent: i can see the problem and have raised a depot ticket",
    "agent: the exchange order is booked and a label was sent",
    "agent: a replacement item leaves the warehouse tomorrow morning",
)

NOTE_WORDS = (
    "draft", "pending", "verify", "customer", "order", "ticket",
    "refund", "delivery", "policy", "depot", "carrier", "billing",
)

SYNONYMS = {
    "order": "purchase",
    "check": "verify",
    "status": "state",
    "delivery": "shipment",
    "refund": "repayment",
    "problem": "issue",
    "arrived": "delivered",
    "asked": "requested",
    "broken": "damaged",
    "item": "product",
}

JSON_BASE = (
    ("tier", "gold"),
    ("currency", "USD"),
    ("region", "us-central"),
    ("channel", "web"),
    ("cart_items", 2),
    ("discount_pct", 10),
    ("loyalty_points", 340),
    ("flags", "beta"),
)


def _seed_for(family, seed):
    return zlib.crc32(family.encode("utf-8")) * 1000003 + seed * 7919 + 17


def _tools_text(tools):
    return " ".join(
        "tool:%s %s" % (name, desc) for name, desc in tools)


def _ts_string(at_minutes):
    seconds = 9 * 3600 + int(at_minutes * 60)
    return "2026-11-22T%02d:%02d:%02dZ" % (
        seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def _rewrite(text, rng):
    out = []
    for token in text.split():
        if token in SYNONYMS and rng.random() < 0.5:
            out.append(SYNONYMS[token])
        else:
            out.append(token)
    return " ".join(out)


def build_trace(family, seed, n_requests=24):
    """Build one seeded session trace with planted ground truth."""
    if family not in SCENARIOS:
        raise ValueError("unknown scenario family: %s" % family)
    rng = random.Random(_seed_for(family, seed))

    session = "sup-%04d" % rng.randint(1000, 9999)
    tools = rng.sample(list(TOOL_CATALOGUE), 6)
    tools_sorted = sorted(tools, key=lambda pair: pair[0])
    tools_canonical = _tools_text(tools_sorted)

    header_volatile = family in HEADER_VOLATILE_FAMILIES
    header_base = ("session=%s model=support-agent-v3 region=us-central"
                   % session)
    header_canonical = header_base + " request=0 ts=2026-01-01T00:00:00Z"

    # Retrieved chunks are fixed for the rewrite family (so the
    # rewrite is the first divergence) and fresh per request else.
    fixed_chunks = None
    if family == "history_rewrite":
        fixed_chunks = []
        for k in range(3):
            frag = "%s %s" % (rng.choice(FRAGMENTS),
                              rng.choice(FRAGMENTS))
            fixed_chunks.append("chunk f%d: %s" % (k + 1, frag))

    json_values = dict(JSON_BASE)
    prev_json_values = None
    turns = []
    requests = []
    at_minutes = 0.0

    for i in range(n_requests):
        if i > 0:
            if family == "long_gap_ttl":
                at_minutes += round(rng.uniform(6.0, 12.0), 2)
            else:
                at_minutes += round(rng.uniform(0.5, 3.0), 2)

        # Header.
        if header_volatile:
            header_text = header_base + " request=%d ts=%s" % (
                i, _ts_string(at_minutes))
            header = Segment("header", "header", header_text,
                             canonical_text=header_canonical,
                             breaker="header_volatile")
        else:
            header = Segment("header", "header", header_base)

        system = Segment("system", "system", SYSTEM_TEXT)

        # Tool definitions.
        if family in TOOL_SHUFFLE_FAMILIES:
            order = list(tools)
            rng.shuffle(order)
            tools_seg = Segment("tools", "tools", _tools_text(order),
                                canonical_text=tools_canonical,
                                breaker="tool_order_shuffle")
        else:
            tools_seg = Segment("tools", "tools", tools_canonical)

        # JSON state blob.
        json_seg = None
        if family in JSON_FAMILIES:
            if family == "json_churn" and i > 0 and rng.random() < 0.3:
                json_values = dict(json_values)
                json_values["cart_items"] = (
                    json_values["cart_items"] + rng.randint(1, 3))
                json_values["loyalty_points"] = (
                    json_values["loyalty_points"] + rng.randint(5, 40))
            keys = list(json_values.keys())
            rng.shuffle(keys)
            shuffled = dict((key, json_values[key]) for key in keys)
            logged = json.dumps(shuffled)
            canonical = json.dumps(json_values, sort_keys=True)
            breaker = None
            if prev_json_values is not None:
                if json_values == prev_json_values and logged != canonical:
                    breaker = "json_key_reorder"
            json_seg = Segment("json_blob", "json_blob", logged,
                               canonical_text=canonical, breaker=breaker)
            prev_json_values = dict(json_values)

        # Retrieved chunks.
        if fixed_chunks is not None:
            retrieved_text = " ".join(fixed_chunks)
        else:
            chunks = []
            for k in range(3):
                frag = "%s %s" % (rng.choice(FRAGMENTS),
                                  rng.choice(FRAGMENTS))
                chunks.append("chunk r%d: %s" % (i * 3 + k + 1, frag))
            retrieved_text = " ".join(chunks)
        retrieved_breaker = None
        if family in RETRIEVED_FIRST_FAMILIES:
            retrieved_breaker = "retrieved_before_static"
        retrieved = Segment("retrieved", "retrieved", retrieved_text,
                            breaker=retrieved_breaker)

        # History: one new turn per request, appended verbatim --
        # except in the rewrite family, whose logged history is a
        # re-worded rendering of the same turns.
        turns.append("%s %s" % (rng.choice(TURN_USER),
                                rng.choice(TURN_AGENT)))
        history_original = " ".join(turns)
        if family == "history_rewrite":
            history = Segment("history", "history",
                              _rewrite(history_original, rng),
                              canonical_text=history_original,
                              breaker="history_rewrite")
        else:
            history = Segment("history", "history", history_original)

        volatile = Segment(
            "volatile", "volatile",
            "scratch step=%d note=%s" % (
                i, " ".join(rng.choices(NOTE_WORDS, k=6))))

        user = Segment("user", "user",
                       "user: %s" % rng.choice(QUESTIONS))

        if family == "retrieved_first":
            segments = [header, retrieved, system, tools_seg,
                        history, volatile, user]
        elif family == "mixed_kitchen_sink":
            segments = [header, retrieved, system, tools_seg, json_seg,
                        history, volatile, user]
        else:
            segments = [header, system, tools_seg]
            if json_seg is not None:
                segments.append(json_seg)
            segments.extend([history, retrieved, volatile, user])

        requests.append(Request(index=i, at_minutes=at_minutes,
                                segments=segments))

    return Trace(family=family, seed=seed, requests=requests)


def trace_to_dict(trace):
    return trace.to_dict()


def trace_from_dict(data):
    return Trace.from_dict(data)
