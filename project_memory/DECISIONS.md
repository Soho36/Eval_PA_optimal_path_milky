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

## Still unresolved before a study-scale lifecycle or sweep

- whether Evaluations consume the whole-tape stream or the pinned cycle-local
  adapter, plus the remaining Evaluation rule boundaries;
- initial MNQ, every scaling threshold, operator, metric, scope, downscaling,
  maximum MNQ, and PA intratrade commission timing;
- aggregate execution/slippage assumptions for copied scaled orders;
- acquisition cadence/caps, renewal/cancellation, pending activation, and
  replacement priority;
- selected external-capital mode, starting cash, lifetime budget, and unfunded
  obligation behavior;
- payout request/approval/receipt timing and open-position handling;
- study-wide same-timestamp ordering outside the locked deterministic fixture;
- objective, horizon, right censoring, rolling cohorts, regimes, and stresses.
