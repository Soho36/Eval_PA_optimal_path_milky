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

16. This study is built to be differenced against the parent staggering study
    at revision `106cfb782c6e573856282095441bb69f23924a55`, arm
    `greedy_to_target` / K=5 / R=1 / `max_headroom`. Seven mechanics below are
    adopted from that arm so PA-book management is the only difference. They
    are adopted for comparability, never as inherited conclusions, and K=5 is
    explicitly not adopted: N stays this study's swept axis 1..20.
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
21. External capital is the parent's through-first-PA bridge seeded with one
    $35 Evaluation fee, just-in-time exact shortfalls only, closing
    irreversibly at the first activation. Consequence to report: PAs 2..N are
    funded only from trading profit and payouts, so high-N arms are capital
    constrained by construction and may not fill the book within the horizon.

## Still unresolved before a study-scale lifecycle or sweep

- the remaining Evaluation rule boundaries, now enumerated as explicit open
  questions in the gate (renewal at the N cap, mid-cycle failure restart, and
  the minimum-day basis at a cycle edge);
- payout request/approval/receipt timing and open-position handling;
- study-wide same-timestamp ordering outside the locked deterministic fixture;
- the economic objective;
- horizon, right censoring, and rolling cohorts;
- regime definitions;
- the remaining stresses (prop-firm failure, rule change); path order is locked
  and execution is a declared non-model.
