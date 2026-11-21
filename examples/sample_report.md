Prefix Cache Audit -- demo report
=================================
Trace: mixed_kitchen_sink-3 (12 requests, 4537 tokens as logged)
Pricing: read 0.30 / write 3.75 / base 3.00 per token; TTL 5.0 min

Per-request divergence (against the previous request):
 req  at(min)   lcp  lost~  diverging   predicted              planted
   1     2.90     3    276  header      header_volatile        header_volatile
   2     5.61     3    302  header      header_volatile        header_volatile
   3     7.36     3    323  header      header_volatile        header_volatile
   4     9.27     3    349  header      header_volatile        header_volatile
   5    11.61     3    372  header      header_volatile        header_volatile
   6    12.13     3    385  header      header_volatile        header_volatile
   7    13.72     3    410  header      header_volatile        header_volatile
   8    15.98     3    430  header      header_volatile        header_volatile
   9    16.91     3    455  header      header_volatile        header_volatile
  10    17.91     3    474  header      header_volatile        header_volatile
  11    20.05     3    495  header      header_volatile        header_volatile

Breaker pairs: 11 of 11; flagged breakers masked behind an earlier divergence: 33
Attributed classes: header_volatile x11
Estimated lost tokens: 4271 (segment-granularity baseline: 3556)
Cache-model lost tokens (requests 2..n): 4271

Replay: as-logged cost 16935.0; canonical cost 6833.4
Recoverable by canonical ordering: 10101.6 (59.6% of input cost)
Cache reads: 0 tokens as logged, 2928 canonical
