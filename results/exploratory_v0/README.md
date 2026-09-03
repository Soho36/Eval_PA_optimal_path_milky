# exploratory_v0 — superseded, retained as evidence

Produced 2026-09-02/03 before three defects were known. Kept for comparison,
not for citation. Do not quote these numbers as study results.

Known defects in the code that produced this output:

1. The runner hard-coded payout before spending and never read the selected
   event-order rank map, so `spend_before_payout` was never executable. 25 of
   110 cohorts raise `Same-timestamp lifecycle phase order regressed`.
2. The loop stopped at `now >= horizon_end_at`, excluding an exit landing
   exactly on the horizon, which the contract says must settle. One accepted
   opportunity (`rr1:22-23:341:1306`) is affected, so every arm reports five
   open batches when only four are genuinely post-horizon. It carried no PA
   copies here, so headline cash is unaffected in this run only.
3. The per-cohort CSV omits owner capital, fees, ending cash and any
   cash-bound versus pipeline-bound measure, so the claim that Evaluation
   pipeline time rather than cash binds at large N is NOT demonstrated by this
   data. It was inferred from the activation plateau alone.

Interpretation errors made when this output was first reported:

- Totals were summed across all six payout policies, which are mutually
  exclusive alternatives, and counted the same 55 starts six times. There is
  no "$2.33M at N=9-12" result. Per-policy best N ranges from 5 to 20.
- No regime split was computed despite the contract requiring one. Every arm
  has a negative median, and the results are tail-driven.
