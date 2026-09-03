# Status

Current state only. Rationale is in `ASSUMPTIONS.md`; values are in
`config/runtime.json`.

## Where the work stands

The engine is executable end to end on the real RR1 tape: gate-to-runtime
bundle, per-Evaluation cycle-local consumer (verified equal to the pinned
behavior lock on real starts), single-cohort runner, and a parallel sweep
driver that is deterministic across worker counts.

`results/exploratory_v0/` holds the first full 20x6 grid. **It is superseded
and must not be cited** — see its README for the three defects and two
interpretation errors it contains.

## Blockers before a citable sweep

1. No regime split is computed, though the contract requires one. The
   exploratory grid showed strong regime dependence that remains unquantified.
2. The `source_constrained_then_mae_first` arm has not been run, so no parent
   comparison is legal.
3. The `spend_before_payout` arm is now executable but has not been run and
   reported.
4. No Pareto reporting exists; results are still single aggregates.

A run while these stand must pass `exploratory=True` and is labelled
exploratory in its own manifest.

## What the corrected engine has measured

- **Correlated deaths are real.** At N=2, 39 of 181 death events killed both
  PAs on the same trade — the copy-to-all signature that staggering at R=1
  cannot produce.
- **Cash binds, not pipeline time.** Measured per cohort: at N=20, cash-bound
  time exceeds pipeline-bound by roughly 55x (8,474 vs 153 days over 12
  cohorts), and `book_full` is 0 days at N>=12, so the book never reaches
  target. An earlier claim to the opposite was inferred from an activation
  plateau and was wrong.
- **A one-tick perturbation is not a small perturbation.** On identical trades
  it costs exactly $1.00 per round turn at 1 MNQ, but across the grid it moved
  totals by +17% to +22% *upward*, because it changes which accounts die when
  and therefore the whole downstream trajectory. The N-curve is not robust to
  it.

## Provenance model

Frozen inputs stay hash-verified: the RR1 import manifest, upstream evidence,
the rules files, and the Evaluation behavior-lock fixture. Local mutable source
and prose are governed by Git plus a working-tree digest recorded in every run
manifest, not by hashes checked into other files. Every run hashes its own
outputs.

Transfer paperwork and parent snapshots live under `archive/` and are not
mandatory reading.
