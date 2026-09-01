# Project

## Objective

Find robust economic policies for progressing from Legacy 25K Evaluations to a
synchronized book of Legacy 25K PAs and withdrawing/reinvesting cash over time.

## Defining distinction

The input strategy first produces the same global one-position opportunity tape
used by the parent Evaluation study. Every eligible active PA then receives a
copy of each accepted opportunity. If ten PAs are active, the event creates ten
account-level trades. There is no router choosing among accounts.

Accounts can diverge because they may activate at different times, have
different balances/payout histories, use different contract counts under a
future scaling rule, or die at different times after such divergence. Without
those differences, copied accounts remain perfectly path-correlated.

## Initial study dimensions

- active PA count, ultimately 1-20;
- Evaluation acquisition and dead-PA replacement;
- payout and reinvestment policy;
- one-or-more-MNQ scaling thresholds;
- external-capital constraints; and
- firm-wide/rule-change concentration stress.

## Out of scope initially

- signal staggering and routing competition;
- dormant PA reserves;
- NinjaTrader order placement or broker-fill simulation;
- non-Legacy account types; and
- claims that parent-project rankings transfer to this model.
