# Project

## Objective

Find robust economic policies for progressing from Legacy 25K Evaluations to a
synchronized book of Legacy 25K PAs and withdrawing/reinvesting cash over time.

## Defining distinction

The verified source tape is selected once into one causal, whole-tape,
one-position PA opportunity stream. Every eligible active PA receives a copy of
each accepted opportunity. If ten PAs are eligible, the event creates ten
account-level copies. Lifecycle consumption is bound to the exact selected row
and ordinal, so a cycle-local or singleton reselection cannot enter the PA book.
There is no router choosing among accounts.

The Evaluation phase uses cycle-local one-position selection reset at each
Evaluation/renewal cycle at 3 MNQ. The upstream behavior lock pins that adapter;
the study runner must still integrate it per Evaluation rather than accept
arbitrary caller-selected offers.

Accounts can diverge through activation time, balances and payouts, MNQ count,
compliance, or prior death. Before those differences, copied accounts remain
perfectly path-correlated.

For the headline 1..20 axis, N is the maintained target number of active PAs
acquired from zero through paid Evaluations and activations. Alive active PAs,
running Evaluations, and pending activations count toward a hard capacity cap of
N. An initial-N active book is diagnostic only.

Phase 1 starts with $35 owner cash for `eval-1`; only that Evaluation's
renewals and activation may receive bridge capital. Owner-net retained cash is
the headline economic measure, with cumulative payout harvest secondary and
unwithdrawn PA equity reported separately.

Completed-trade path order is reported in three lifecycle-wide scenarios:
source-constrained plus all ambiguous MAE-first, all ambiguous MFE-first, or a
reproducible seeded assignment. The seed is an imputation, not observed truth.

## Study dimensions

- every active-PA count from 1 through 20;
- phase-1 greedy acquisition and pipeline replacement, followed by explicitly
  selected alternative acquisition/replacement policies for the full study;
- all six payout candidates and reinvestment timing;
- a flat one-MNQ phase-1 baseline, followed by explicitly selected MNQ scaling
  thresholds and scope;
- the selected first-PA-chain external-capital constraint;
- rolling cohorts and independently defined regimes; and
- the three path-order arms and a full-axis one-tick execution sensitivity;
  the deterministic `spend_before_payout` ordering arm; and firm-failure and
  rule-change stresses remain declared non-models.

## Out of scope

- signal staggering and routing competition;
- dormant PA reserves;
- inherited `max_headroom`, K=2/S=1, inventory, fill-rate, or optimum claims;
- NinjaTrader order placement or broker-fill simulation;
- non-Legacy account types; and
- an integrated sweep before every active gate blocker is resolved and tested.
