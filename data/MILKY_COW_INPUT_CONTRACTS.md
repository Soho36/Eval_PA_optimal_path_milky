# Milky-cow input and model-contract audit

Audit date: 2026-09-01 (Europe/Tallinn).

## Verdict

The imported evidence is intact, and the PA copy-to-all distribution can be
implemented and tested in isolation. An integrated lifecycle or parameter sweep
is not authorized yet because the scaling schedule, Evaluation consumer mode,
acquisition/replacement policies, external-capital budget, payout timing, event
order, and economic objective are unresolved.

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
prove membership in the accepted partition.

The pinned Evaluation adapter is different: it restarts one-position selection
at each Evaluation and renewal boundary. Whole-tape selection and cycle-local
selection differ for some cohorts. Therefore the Evaluation fixture is an
upstream behavior lock only until `evaluation_consumer_mode` is selected.

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
aggregation, maximum MNQ, and linear/nonlinear outcome assumption. No schedule
is selected yet. The undated four-mini excerpt does not by itself authorize a
40-MNQ conversion.

## Acquisition, replacement, and capital boundary

An acquired or replacement PA must traverse Evaluation purchase/renewal, pass,
activation funding, and strict post-activation eligibility. A death never
creates an instant PA. All running Evaluations and pending activations must be
visible capacity commitments if the chosen PA-count estimand is a target/cap.
External contributions must be timestamped, purpose-tagged, budget checked, and
cash-reconciled. No acquisition, replacement, or capital policy is selected yet.

## Payout and reporting boundary

The six v2 payout definitions are candidates and match the milky contract.
The older six accumulation-trigger policies named in the copied audit/upstream
manifest are stale. Atomic versus pending payout timing and its treasury
availability remain unresolved. The copied 720-day and 2022-regime conclusions
are candidate design references, not inherited findings.
