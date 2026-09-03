# Assumptions

Why the model is shaped the way it is. Values live in `config/runtime.json`;
this file is never loaded by code. Current state is in `STATUS.md`.

## What is being studied

Whether a synchronized book of 1–20 Legacy 25K PAs can be grown and harvested
economically when every eligible active PA receives the same accepted signal.
The study exists to be differenced against the parent staggering study at
`Eval_PA_optimal_path` revision `106cfb782c6e573856282095441bb69f23924a55`,
arm `greedy_to_target` / K=5 / R=1 / `max_headroom`. Every mechanic below is
adopted to hold everything except PA-book management constant.

## Adopted from the parent, for comparability

- **Evaluation consumer.** The parent's cycle-local one-position adapter,
  re-selected at every 30-day renewal boundary, at 3 MNQ. This deliberately
  differs from the PA book's single never-reset whole-tape selection; the two
  phases never share a selector. Verified equal to the pinned behavior lock.
- **Commission** charged only in closing net P&L.
- **Acquisition** is greedy in time, not in batch: at most one Evaluation per
  decision, whenever cash allows and the pipeline is below N.
- **Replacement** is not an independent policy — a death drops the pipeline
  below N and the acquisition rule buys.
- **Mid-cycle Evaluation failure** goes dormant until its 30-day boundary and
  keeps holding its pipeline slot. Parent-verified: the parent's simulator
  never assigns a failure status, so a dormant Evaluation still counts as
  running.
- **Payout timing** is atomic request/approval/removal/receipt, zero delay.

K=5 is explicitly **not** adopted: N is this study's swept axis 1–20.

## Chosen here

- **No PA scaling in phase 1.** Every eligible PA trades 1 MNQ at every entry.
  The Evaluation still runs 3 MNQ; "no scaling" is a PA-only decision.
- **External capital** is the first-PA-chain bridge: a $35 owner seed buys
  `eval-1`, and only `eval-1` renewals and its activation may receive
  just-in-time exact shortfalls. The bridge closes irreversibly at that
  activation, so PAs 2..N are earned from treasury proceeds.
- **Headline metric** is owner-net retained cash: treasury cash minus all
  owner-supplied capital, which for a reconciled ledger equals payout receipts
  minus fees paid. Cumulative payout harvest is secondary.
- **Event order** is one canonical declared ranking — settle, realize, spend,
  commit — with `spend_before_payout` as the deterministic sensitivity arm.
  Random ordering was rejected: it would break reproducibility, break parent
  comparability, and hide any real effect inside variance.
- **Horizon crossing.** An entry before the cutoff is admitted; an exit
  *strictly* after it is not settled, so the batch stays open and unscored. An
  exit landing exactly on the horizon does settle.
- **Cohorts** start at the first accepted-opportunity session of each calendar
  month, and only starts with a complete horizon are used.

## Known limits, stated rather than hidden

- **Frictionless execution is not neutral here.** The parent filled 1 MNQ per
  signal at R=1; copy-to-all fills N simultaneously, so the error grows with N,
  the study axis itself. Bias direction: `favors_high_n`. The one-tick-per-side
  sensitivity is implemented and must be run before any headline N claim.
- **Cohorts overlap.** They are separate historical opportunities, not
  independent samples. No confidence interval across them is valid.
- **The six payout policies are alternatives.** They must never be summed, and
  the same starts must not be counted once per policy.
- **Results are tail-driven.** Medians are negative across the grid; report a
  Pareto view over average cash, profitable-start share, downside and worst
  regime rather than a single ranking.
- **Not modelled:** prop-firm failure, rule change, pending-order and broker
  fill lifecycle, payout consistency, denials and delays.
