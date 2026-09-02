# Architecture

## Executable foundation

- `inputs.py`: verifies RR1, normalizes Tallinn time, selects and validates the
  causal whole-tape stream, caches accepted-opportunity evidence records, and
  applies the three explicit intratrade path scenarios.
- `cohorts.py`: derives deterministic monthly session starts and separates
  fully observed horizons from tape-censored starts.
- `evaluation_lock.py`: executes the pinned upstream cycle-local Evaluation
  behavior fixture; it is not yet the integrated consumer.
- `contracts.py`: explicit scaling, pipeline-cap accounting, acquisition, and
  death-count-bounded replacement primitives.
- `copy_to_all.py`: copies accepted opportunities to every eligible PA,
  snapshots entry state, settles the outstanding batch once at exact exit, and
  maintains payout-period state.
- `evaluation.py`: stateful, treasury-independent Evaluation trade, failure,
  pass, cycle, and renewal mechanics; it does not choose the consumer adapter.
- `payouts.py`: exact Legacy 25K eligibility/amount execution for the six
  candidate policies with atomic PA mutation preflight.
- `lifecycle.py`: thin deterministic coordinator that binds the exact PA stream
  and composes treasury, Evaluation, activation, copies, payouts, deaths, and
  replacement intents for contract traces, including unfunded closure/backlog
  behavior and one purchase decision per timestamp. It is not a sweep engine.
- `treasury.py`: starting cash, exact-shortfall capital authorization,
  irreversible bridge closure, cash-ledger reconciliation, and explicit owner-
  capital, retained-cash, and payout-harvest metrics.
- `provenance.py`: transfer and selective-derivative hash verification.

Files under `reference/shared_source/` remain evidence and are never imported by
the active package.

## Study-scale pipeline still to implement

1. integrate the selected cycle-local Evaluation consumer per account;
2. build one gate-to-runtime policy bundle and configurable event queue;
3. resolve bridge scope, headline objective, order sensitivity, and
   horizon-crossing treatment;
4. extend the coordinator through one real-tape N=1 cohort and result manifest;
5. issue one outstanding account copy to every eligible PA per accepted global
   opportunity and settle it at exit;
6. process deaths, payouts, treasury receipts, and future Evaluation intents in
   the selected event order; and
7. report rolling-cohort economics, account divergence/correlation, regimes,
   and stresses for each PA count and policy candidate.

Global-opportunity count and account-copy count stay separate. Deterministic PA
ID order is reporting/event order only, never routing priority.
