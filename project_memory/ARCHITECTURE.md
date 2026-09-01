# Architecture

## Executable foundation

- `inputs.py`: verifies RR1, normalizes Tallinn time, selects and validates the
  causal whole-tape stream, and emits accepted-opportunity evidence records.
- `evaluation_lock.py`: executes the pinned upstream cycle-local Evaluation
  behavior fixture; it is not yet the integrated consumer.
- `contracts.py`: explicit scaling, pipeline-cap accounting, acquisition, and
  death-count-bounded replacement primitives.
- `copy_to_all.py`: copies accepted opportunities to every eligible PA,
  snapshots entry state, and settles the outstanding batch once at exact exit.
- `treasury.py`: starting cash, exact-shortfall capital authorization,
  irreversible bridge closure, and cash-ledger reconciliation.
- `provenance.py`: transfer and selective-derivative hash verification.

Files under `reference/shared_source/` remain evidence and are never imported by
the active package.

## Intended integrated pipeline (not implemented)

1. choose and test the Evaluation consumer and rule boundaries;
2. select a causal scaling schedule and settlement accounting contract;
3. select acquisition, replacement, payout, capital, and event-order policies;
4. simulate Evaluations and activation obligations through treasury;
5. issue one outstanding account copy to every eligible PA per accepted global
   opportunity and settle it at exit;
6. process deaths, payouts, treasury receipts, and future Evaluation intents in
   the selected event order; and
7. report rolling-cohort economics, account divergence/correlation, regimes,
   and stresses for each PA count and policy candidate.

Global-opportunity count and account-copy count stay separate. Deterministic PA
ID order is reporting/event order only, never routing priority.
