# Milky-cow input and model-contract audit

Audit date: 2026-09-02 (Europe/Tallinn).

## Verdict

The imported evidence is intact, copy-to-all and a deterministic N=1/N=2
contract lifecycle are executable, and the phase-1 flat-one-MNQ, close-only,
greedy-pipeline, first-chain-capital, atomic-payout baseline is selected. The
phase-1 user decisions are resolved. A study-scale sweep remains blocked by
implementation of the per-Evaluation consumer, gate-to-runtime bundle,
study-scale horizon/reporting integration, real-tape N=1 manifest, execution-
cost sensitivity, and runner.

The controlling PA overlay is
`rules/MILKY_COW_COPY_TO_ALL_RULES.txt`, and the active executable foundation
gate is `config/milky_cow_contract_gate.json`. The transferred
`config/milky_cow_study_contract.json` is a frozen initial scope record, not a
second active runtime config. The copied parent rule, audit, input contract, and
baseline config are preserved evidence and must not be loaded wholesale.

## Transfer and raw-input verification

The immutable transfer manifest has 96 entries and 2,032,359 recorded bytes.
All 73 parent-snapshot artifacts match. The only differences are the user's
intentional seven-byte `.gitignore` and deletion of the one-use chat prompt;
they are bound by `manifests/transfer_verification_20260901.json`.

The nested RR1 import contains 23 trade and 23 stats files, 1,725,388 bytes and
12,658 trade rows. Every current file matches its individual SHA-256, every
trade/stats count and P&L total agrees, and the combined selection digest is
`1bf2f1c83fe96bf5b86653583f33f52c35631cf0ea561566e0dcb35756274f7e`.
The files were ignored/untracked upstream, so their exact bytes are evidence but
their generator lineage is not proven.

## Global opportunity contract

The PA phase consumes a single materialized one-position stream selected from
the whole verified tape with causal order
`(entry_at, window_order, source_row, ticket)` and occupancy
`[entry_at, exit_at)`. This produces the audited 9,299 accepted and 3,359
blocked offers. The stream is exogenous to PA count and account state. Each PA
book input is an accepted-opportunity record carrying the selector identity,
accepted-stream digest, ordinal, and raw-offer count; a bare TradeOffer does not
prove membership in the accepted partition. The lifecycle additionally binds
the exact selected offer at that ordinal and monotonic consumption, preventing
singleton or cycle-local reselection from manufacturing PA input evidence.

There is one accepted zero-duration RR1 opportunity. Its special executable
suborder is Evaluation entry, PA entry, PA settlement, then Evaluation
settlement, after earlier positive-duration exits and before payouts. It cannot
change its own eligibility.

The pinned Evaluation adapter is different: it restarts one-position selection
at each Evaluation and renewal boundary. Whole-tape selection and cycle-local
selection differ for some cohorts. That cycle-local three-MNQ adapter is selected
for phase 1; the fixture is its upstream behavior lock, and the integrated runner
must still enforce it independently for each Evaluation.

## Parent fields that are forbidden in the active PA model

The active model must not consume parent PA fields or conclusions for
`R`, `K`, `S`, `max_headroom`, routed/selected PA IDs, busy-seat
capacity, standby promotion, dormant PA inventory, base-stock K+S, fill rate,
congestion loss, inventory-grid rankings, or K=2/S=1. Deterministic PA-ID order
is reporting order only.

## Copy and activation contract

At a global opportunity entry, each alive PA with
`activation_at < entry_at` receives one account-level copy. Activation at the
same timestamp is excluded. With no configured account-level compliance block,
global opportunity count is one and account-copy count is exactly the number of
eligible PAs. Every activated live PA is active; there is no spare role. Each
copy records its scaling metric and prior/selected MNQ at entry. The batch is
outstanding until exact `exit_at` and may settle once. An intratrade liquidation
does not receive the source completed-trade P&L because its actual liquidation
fill is absent from the tape.

## Scaling contract boundary

A scaling policy must provide a complete, validated schedule and explicitly name
its metric, inclusive/exclusive comparison, entry-time state snapshot,
downscaling behavior, per-account or synchronized scope, synchronized
aggregation, maximum MNQ, and linear/nonlinear outcome assumption. Phase 1 uses
one per-account MNQ at every entry with a maximum of one and linear outcomes.
Threshold scaling remains a later phase; the undated four-mini excerpt does not
authorize a 40-MNQ conversion.

## Completed-trade path boundary

The tape does not observe MAE/MFE order. One-sided cases and two-sided cases
closing at MAE have a settlement-effective constrained order. Two-sided cases
closing at MFE remain ambiguous because an earlier MFE-to-MAE excursion is
possible, as do closes strictly between extrema. The 5,029 raw ambiguities
partition into 3,722 accepted and 1,307 blocked offers. Every lifecycle scenario
must apply the same all-MAE-first, all-MFE-first, or seeded ambiguous-order arm
to Evaluation and PA and report phase-specific changes from the seeded arm.

## Acquisition, replacement, and capital boundary

An acquired or replacement PA must traverse Evaluation purchase/renewal, pass,
activation funding, and strict post-activation eligibility. A death never
creates an instant PA. For the headline axis, N is the maintained active-PA
target acquired from zero, and active + running Evaluation + pending activation
commitments may never exceed N. Initial-N active is a diagnostic only.
External contributions must be timestamped, purpose-tagged, budget checked, and
cash-reconciled. Phase 1 greedily buys at most one Evaluation per unique
timestamp toward N; death replacement shares that pipeline, and residual
unfunded backlog cannot pause trading. The $35 owner seed buys `eval-1`.
Only that Evaluation's renewal and activation shortfalls may receive bridge
capital; every other obligation requires treasury cash, and `eval-1`
activation closes the bridge irreversibly.

## Payout and reporting boundary

The six v2 payout definitions are candidates and match the milky contract.
The older six accumulation-trigger policies named in the copied audit/upstream
manifest are stale and are excluded from the exact six-policy phase-1 axis.
Payouts are atomic at 23:59 after normal same-day trading; phase 1 has no payout-
55 starts from 79 represented months. The copied 720-day and regime conclusions
remain candidate design references, not inherited findings. Treasury components
and both cash metrics are executable; owner-net retained cash is headline and
cumulative payout harvest is secondary.

If a PA has an outstanding copy at 23:59, only that PA's payout check defers and
its payout-period state remains unchanged; an unaffected active PA can still
pay. The verified stream has 67 such trades crossing 97 total 23:59 phases.
After settlement, same-day realized P&L counts at the next payout phase.

The deterministic ordering sensitivity is `spend_before_payout`. At the
720-day cutoff, a causally admitted trade exiting later remains open and
unscored, with no invented mark-to-market or post-horizon outcome.
