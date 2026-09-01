# Decisions

## Locked at project creation

1. Account type is Legacy 25K only.
2. Source timestamps are interpreted in `Europe/Tallinn`, DST-adjusted.
3. Evaluation uses the source strategy's global one-position opportunity
   behavior.
4. Every accepted global PA opportunity is copied to every eligible active PA.
5. A PA activated at timestamp `t` is first eligible only for entries strictly
   after `t`.
6. There is no staggering, routing competition, `max_headroom` selection, or
   dormant reserve role.
7. The six payout policies are candidates, not inherited optima.
8. Parent code must be imported selectively with provenance and parity tests.

## Must be decided before the integrated sweep

- the initial MNQ count and every scaling threshold;
- whether scaling is determined per account or synchronized across the book;
- whether and how dead PAs are replaced;
- how Evaluation inventory is financed and capped;
- whether copied orders are assumed to have identical completed-trade outcomes
  at larger aggregate size;
- the external-capital budget and objective function; and
- how prop-firm/rule-change concentration risk is stressed.
