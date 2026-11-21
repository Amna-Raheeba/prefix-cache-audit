# Evaluation summary

48 seeded traces (24 requests each, 1104 consecutive pairs), planted ground truth throughout. Pricing: read 0.30 / write 3.75 / base 3.00 per token; TTL 5.0 min.

## Recovery by scenario family

| family | logged cost | canonical cost | recoverable |
|---|---|---|---|
| stable | 82625.4 | 82625.4 | 0.0% |
| header_clock | 262542.0 | 83086.8 | 68.4% |
| tool_shuffle | 229909.8 | 82967.4 | 63.9% |
| json_churn | 210220.2 | 129241.8 | 38.5% |
| history_rewrite | 196117.8 | 83068.2 | 57.6% |
| retrieved_first | 262677.0 | 83111.4 | 68.4% |
| mixed_kitchen_sink | 272700.0 | 84136.8 | 69.1% |
| long_gap_ttl | 263136.0 | 263136.0 | 0.0% |

Pooled recoverable share of input cost: **49.9%**.

## Breaker detection (first-divergence classifier)

Overall: precision **1.000**, recall **0.999**, F1 **0.999** (tp 922, fp 0, fn 1).

| class | precision | recall | tp | fp | fn |
|---|---|---|---|---|---|
| header_volatile | 1.000 | 1.000 | 276 | 0 | 0 |
| tool_order_shuffle | 1.000 | 1.000 | 276 | 0 | 0 |
| json_key_reorder | 1.000 | 1.000 | 95 | 0 | 0 |
| history_rewrite | 1.000 | 0.993 | 137 | 0 | 1 |
| retrieved_before_static | 1.000 | 1.000 | 138 | 0 | 0 |

Flagged breakers masked behind an earlier divergence: 413.

## Estimator accuracy (vs the cache model)

| estimator | lost-token MAE | lost-token rel err | recoverable-cost rel err |
|---|---|---|---|
| audit | 201.3 | 0.018 | 0.127 |
| baseline | 2033.6 | 0.373 | 0.814 |

## Where the lost tokens belong (planted class)

| planted primary | share of lost tokens |
|---|---|
| header_volatile | 30.7% |
| history_rewrite | 10.8% |
| json_key_reorder | 7.6% |
| retrieved_before_static | 15.1% |
| tool_order_shuffle | 28.1% |
| unflagged_change | 7.7% |
