# State

## Current status

Foundation contracts and a deterministic N=1/N=2 lifecycle vertical slice are
executable. No study-scale lifecycle runner, parameter sweep, economic result,
optimum, or policy ranking exists.

Verified and implemented:

- 73/73 imported parent artifacts exact, with two user-confirmed starter
  deviations recorded separately;
- RR1 12,658 raw -> 9,299 accepted / 3,359 blocked, accepted-stream digest,
  exact ordinal/offer lifecycle binding, and the one zero-duration event order;
- 5,029 raw and 3,722 accepted path-ambiguous offers, including the full seeded
  assignment digest; Tallinn DST fold/gap normalization; and three Evaluation
  behavior-lock episodes;
- copy-to-all parity for N=0..3, strict activation, compliance recording,
  correlated deaths, accepted-stream membership type, entry-state snapshot,
  and one-shot exact-exit settlement;
- phase-1 flat one-MNQ scaling plus executable threshold, scope, timing and
  boundary primitives; phase-2 threshold values remain a later user choice;
- pipeline-cap, acquisition and death-count-bounded replacement primitives,
  including unfunded-renewal closure, retryable death backlog and one-decision
  per-timestamp guards;
- none/fixed-budget/time-based and selected first-PA-chain capital primitives,
  explicit Evaluation lineage, irreversible closure, no partial top-up, ledger
  reconciliation, and owner-capital, retained-cash and payout-harvest metrics;
- headline N semantics as a maintained active target acquired from zero with
  active + running Evaluation + pending activation hard-cap accounting;
- stateful Evaluation, six-candidate payout, and thin lifecycle composition,
  including pending activation, renewal preflight, pre-mutation payout atomicity,
  per-PA open-copy payout deferral, N=1 replacement, N=2 divergence, and
  treasury reconciliation fixtures;
- active gate coverage for every PA count 1..20 and the exact six payout
  candidates;
- cached accepted-opportunity evidence and deterministic monthly cohort
  generation: 55 complete 720-day starts from 79 represented months, plus an
  executable leave-open-unscored horizon classifier;
- canonical and `spend_before_payout` deterministic event-order modes; and
- source/local implementation provenance verification.

The canonical suite discovers and passes 92 tests, including transfer and
provenance verification. All phase-1 user choices are resolved. The
gate-to-runtime bundle (`policy_bundle.py`), the per-Evaluation cycle-local
consumer (`evaluation_consumer.py`, verified equal to the pinned behavior lock)
and a single-cohort runner (`study_runner.py`) now exist, and the first
real-tape slice is recorded in `results/n1_real_tape_slice.json`: N=1,
`minimum_500_always`, 55 monthly cohorts, deterministic across repeat runs.

The central-arm sweep has now run: 120 arms (N=1..20 x six payout candidates),
6,600 cohort runs, 12.6 minutes on 7 workers, deterministic across worker
counts. Descriptively, total owner-net retained cash rises to a plateau near
N=9-12 and falls by N=19-20, while the share of profitable cohorts falls
monotonically from 130/330 to 15/330; activations plateau near 2,500-2,700,
confirming Evaluation pipeline time rather than cash as the large-N constraint.
These are observations, not conclusions: the median arm is -160 everywhere, the
cohorts overlap, and only the seeded-coin arm at frictionless execution has
run.

Still outstanding: the one-tick-per-side full-N sensitivity, the mae_first arm
required for any parent comparison, and the executed spend_before_payout arm. Two runner defects found by the
slice and fixed under regression test: session closes were anchored on the
audit log, so an earning PA with thousands in equity took zero payouts; and an
unfundable obligation was retried at every timestamp, stalling the clock.

The corrected raw accepted-opportunity diagnostic has 6,482 fully observed
720-day starts with median net gain about $6,602 (min -$259, max $21,024);
the whole 2,384-day accepted stream nets $27,683 at one MNQ. These figures are
not lifecycle or monthly-cohort results.

Four consequences to carry into reporting:

- frictionless execution is biased `favors_high_n`, so the required one-tick-
  per-side full-N sensitivity must precede strong N conclusions;
- book-fill reports must measure cash-bound versus Evaluation-pipeline-bound
  time rather than infer the answer from raw tape profit;
- phase 1 has normal payout-day trading and no sit-out state; 67 accepted trades
  cross at least one payout close and create 97 per-night deferral points before
  multiplying by the number of copied PAs; and
- owner-net retained cash is headline, cumulative payout harvest is secondary,
  and surviving unwithdrawn equity remains separate.
