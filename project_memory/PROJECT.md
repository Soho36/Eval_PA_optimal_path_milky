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

The upstream Evaluation behavior lock instead resets one-position selection at
each Evaluation/renewal cycle. The integrated Evaluation consumer remains an
explicit decision; the behavior lock is not silently the lifecycle baseline.

Accounts can diverge through activation time, balances and payouts, MNQ count,
compliance, or prior death. Before those differences, copied accounts remain
perfectly path-correlated.

For the headline 1..20 axis, N is the maintained target number of active PAs
acquired from zero through paid Evaluations and activations. Alive active PAs,
running Evaluations, and pending activations count toward a hard capacity cap of
N. An initial-N active book is diagnostic only.

Completed-trade path order is reported in three lifecycle-wide scenarios:
source-constrained plus all ambiguous MAE-first, all ambiguous MFE-first, or a
reproducible seeded assignment. The seed is an imputation, not observed truth.

## Study dimensions

- every active-PA count from 1 through 20;
- Evaluation acquisition and dead-PA replacement;
- all six payout candidates and reinvestment timing;
- explicitly selected MNQ scaling thresholds and scope;
- external-capital constraints;
- rolling cohorts and independently defined regimes; and
- trading, aggregate-execution, firm-failure, and rule-change stress.

## Out of scope

- signal staggering and routing competition;
- dormant PA reserves;
- inherited `max_headroom`, K=2/S=1, inventory, fill-rate, or optimum claims;
- NinjaTrader order placement or broker-fill simulation;
- non-Legacy account types; and
- an integrated sweep before every active gate blocker is resolved and tested.
