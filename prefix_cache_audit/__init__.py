"""Prefix Cache Audit.

Reads an agent system's request traces, finds exactly which prompt
segment breaks prefix-cache reuse, attributes the lost cache tokens
to the responsible segment class -- a volatile header field, a
shuffled tool list, a re-serialised JSON blob, a rewritten history,
retrieved text parked in front of static text -- and prices what a
canonical stable ordering would recover, by replaying the trace
through a declared cache model.
"""

__version__ = "0.1.0"
