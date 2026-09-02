# Decisions

## Locked

1. Account type is Legacy 25K only.
2. Source timestamps use `Europe/Tallinn`, DST-adjusted.
3. The PA book consumes the whole verified tape selected once with causal order
   `(entry_at, window_order, source_row, ticket)` and `[entry_at, exit_at)`
   occupancy. Current parity is 12,658 raw, 9,299 accepted, 3,359 blocked.
4. Every accepted PA opportunity is copied to every eligible active PA.
5. A PA activated at `t` is first eligible only for entries strictly after `t`.
6. There is no staggering, routing competition, `max_headroom`, requested R,
   K/S inventory, fill-rate congestion, or dormant PA reserve.
7. PA copy input carries accepted-stream identity and ordinal. Entry scaling
   state is snapshotted; the lifecycle also binds the exact selected offer at
   that ordinal and consumes monotonically. The batch settles once at exact
   `exit_at`.
8. An intratrade liquidation does not receive unknowable completed-trade P&L.
9. Replacement creates Evaluation purchase intents and never an instant PA.
10. Outside capital is explicit and cash-reconciled; a through-first-PA bridge
    uses a treasury-owned irreversible activation latch.
11. The six payout policies are candidates, not inherited optima.
12. Parent code is selectively adapted with source revision/hash and parity
    fixtures. Imported parent artifacts remain immutable.
13. Headline N means a maintained active-PA target acquired from zero. Alive
    active PAs, running Evaluations, and pending activations each consume one of
    N hard-cap commitments. Initial-N active runs are diagnostic only.
14. Completed-trade path order has three lifecycle-wide scenarios. One-sided
    and terminal-at-MAE cases retain their settlement-effective constraint;
    terminal-at-MFE and interior two-sided cases remain ambiguous. Evaluation
    and PA use the same arm, with the seeded arm only a reference imputation.
15. The one RR1 zero-duration opportunity uses an explicit entry/settlement
    suborder after earlier positive-duration exits and before payouts. An
    Evaluation pass remains pending until the later activation phase spends
    cash; it never activates inside Evaluation settlement.

16. The parent staggering study at revision
    `106cfb782c6e573856282095441bb69f23924a55` is a descriptive composite
    benchmark, not a single-difference causal arm. Its PA phase uses 12,658
    concurrent raw offers and one routed R=1 copy; this study uses 9,299 global
    opportunities and up to N simultaneous copies. Adopted common mechanics aid
    comparability, but K=5, routing, and parent conclusions are not adopted.
17. Evaluations use the parent's cycle-local one-position adapter, re-selected
    at every 30-day renewal boundary, at 3 MNQ. This deliberately differs from
    the PA book's single never-reset whole-tape selection; the two phases never
    share a selector. Phase-1 "no scaling" is a PA-only decision.
18. Phase 1 has no PA scaling: every eligible PA trades 1 MNQ at every entry.
    Round-turn commission is charged only in closing net P&L.
19. Aggregate execution and slippage are not modeled in phase 1. Unlike the
    parent, this is not a neutral omission: the parent filled 1 MNQ per signal
    at R=1 while copy-to-all fills N simultaneously, so the error grows with N,
    the study axis itself. Recorded with bias direction `favors_high_n`.
20. Acquisition is greedy in time, not in batch: at most one Evaluation per
    decision, whenever cash allows and the pipeline is below N. Replacement is
    not an independent policy — a death drops the pipeline below N and the
    acquisition rule buys.
21. Phase 1 starts with $35 owner cash and an irreversible first-activation
    bridge latch. Whether the bridge is time-based for every permitted
    obligation before that activation or restricted to the first PA's own
    Evaluation/renewal/activation chain remains a user decision.

22. Evaluation boundaries: a renewal fee is paid only when the pipeline
    excluding that Evaluation is below N; a mid-cycle drawdown breach stops
    trading and stays dormant until the 30-day boundary, then restarts fresh
    without carrying state (parent parity); the trading day cuts at
    `Europe/Tallinn` 00:00, with Evaluation days on entry date and PA realized
    P&L on exit date.
23. Phase 1 allows normal PA trading on a payout day. All completed trades
    settle first; eligibility and an atomic payout are evaluated at 23:59
    Tallinn, and same-day realized P&L counts. There is no sit-out state.
24. Treasury reports starting owner cash, later contributions, payouts, fees,
    and ending cash. Owner-net retained cash equals ending cash minus owner
    capital, or payouts minus fees. Cumulative payout harvest and owner-net
    retained cash are both executable; the user must choose the headline.
25. Cohorts start at 01:00 Tallinn on the first accepted-opportunity session of
    each calendar month and require a complete 720-day future interval. The
    verified tape gives 55 complete monthly cohorts (79 before filtering) and
    1,179 complete daily session starts. All three path arms imply 19,800
    primary grid runs. Cohorts overlap and are not independent samples.
26. Horizon is 720 days primary, matching the parent so the comparison is
    valid, plus a 1,440-day book-fill diagnostic on selected N. At horizon,
    withdrawn cash and un-withdrawn equity are reported separately and running
    Evaluations are sunk fees, never an asset.
27. Regimes are a reporting partition only: the parent's two calendar windows
    plus a `candle_range` volatility tercile. Directional bull/bear/sideways
    regimes are deferred — the frozen tape has no price series, and deriving
    direction from trade outcomes would make regime findings tautological.
28. Prop-firm failure and rule-change stresses are not modeled, matching the
    parent.

29. A failed Evaluation stays dormant and keeps its pipeline slot until its
    renewal boundary, and keeps paying renewal fees. This is parent parity,
    verified in code: the parent's simulator never assigns a failure status —
    `EvaluationRuntime.status` leaves `active` only for `passed` or
    `closed_unpaid_renewal`, and `running_evaluation_count()` counts
    `active`. Report blocked-slot days per N, since correlated deaths can
    block several slots at once.
30. Same-timestamp events use one canonical declared order: settle, realize,
    spend, commit. Random ordering is rejected — it would break the
    byte-reproducible digests the study rests on, break parent comparability,
    and hide any real ordering effect inside variance. At least one pair does
    bind: payout must precede renewal, activation and purchase, because payout
    cash funds those same-instant fees. Insensitivity is measured once with a
    permuted-order arm rather than assumed. `_PHASE_RANK` is asserted equal to
    the gate's declared order by test.
31. Payout timing is parent parity: atomic request, approval, balance removal
    and treasury receipt, zero delay, no pending state, no denials. A terminal
    sweep is a censoring valuation, never a policy. The $1k-per-$5k trigger is
    excluded from phase 1 because the requested axis is exactly the six-policy
    catalog. On 6,482 fully observed accepted-opportunity starts, the descriptive
    720-day median is about $6,602 and 65.4% reach $5,000; this does not prove a
    lifecycle ranking. Reconsider only if phase 2 scales above 1 MNQ.

## Still unresolved before a study-scale lifecycle or sweep

Four user decisions remain:

1. bridge scope: time-based until first activation, or first-PA chain only;
2. headline cash metric: owner-net retained cash, or cumulative payout harvest;
3. deterministic order sensitivity: spend-before-payout, or
   activation-before-renewal; and
4. horizon-crossing trades: require entry and exit inside the horizon, settle
   after the horizon and label the cohort extended, or admit the trade causally
   and leave its still-open outcome unscored at the cutoff.

Implementation still required: a gate-to-runtime bundle, the per-Evaluation
cycle-local consumer, a configurable event queue, one real-tape N=1 result
manifest, and then the study runner.
