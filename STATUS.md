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

Mirrors `config/runtime.json`, which is the enforced copy.

1. The two-model execution comparison has not been run at scale. One-tick is
   implemented and now reaches **both** phases; only smoke grids have run it.
2. No regime split is computed, though the contract requires one. The
   exploratory grid showed strong regime dependence that remains unquantified.
3. The `source_constrained_then_mae_first` arm has not been run, so no parent
   comparison is legal.
4. The `spend_before_payout` arm is executable but has not been run and
   reported.
5. No Pareto reporting exists; results are still single aggregates.

A run while these stand must pass `exploratory=True` and is labelled
exploratory in its own manifest.

## What the corrected engine has measured

- **Correlated deaths are real.** At N=2, 39 of 181 death events killed both
  PAs on the same trade — the copy-to-all signature that staggering at R=1
  cannot produce.
- **Cash binds, not pipeline time.** Measured per cohort with complete
  accounting: at N=20 over 12 cohorts, cash-bound 8,476 days versus
  pipeline-bound 153, `book_full` 0 and `growth_ready` 11.9 — the four buckets
  now sum to the cohort length exactly. The book never reaches target at
  N>=12. An earlier claim to the opposite was inferred from an activation
  plateau and was wrong.
- **A one-tick cost is exactly $1.00 per round turn at 1 MNQ**, verified on
  identical trades in both phases. An earlier report that it moved grid totals
  by +17% to +22% is **withdrawn**: PA settlement was not receiving the
  execution model, so that perturbation touched Evaluations only and said
  nothing about copy-to-all sensitivity. The corrected two-model comparison has
  not yet been run at scale.

## Provenance model

Frozen inputs stay hash-verified: the RR1 import manifest, upstream evidence,
the rules files, and the Evaluation behavior-lock fixture. Local mutable source
and prose are governed by Git plus a working-tree digest recorded in every run
manifest, not by hashes checked into other files. Every run hashes its own
outputs.

Transfer paperwork and parent snapshots live under `archive/` and are not
mandatory reading.
