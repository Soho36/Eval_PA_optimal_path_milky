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
- explicit per-account/synchronized scaling primitives and boundary tests,
  with no schedule selected;
- pipeline-cap, acquisition, death-count-bounded replacement intent primitives;
- none/fixed-budget/through-first-PA capital primitives, starting cash,
  irreversible closure, no partial top-up, and ledger reconciliation;
- headline N semantics as a maintained active target acquired from zero with
  active + running Evaluation + pending activation hard-cap accounting;
- stateful Evaluation, six-candidate payout, and thin lifecycle composition,
  including explicit pending activation, renewal preflight, payout atomicity,
  N=1 replacement, N=2 divergence, and treasury reconciliation fixtures;
- active gate coverage for every PA count 1..20 and the exact six payout
  candidates;
- source/local implementation provenance verification; and
- seven gate fields resolved for parity with the parent baseline arm, each
  buildable from the gate into the primitive it names: the cycle-local
  Evaluation consumer, flat 1 MNQ, close-only commission, declared
  execution non-model, greedy-in-time acquisition, emergent replacement, and
  the through-first-PA capital bridge.

`scripts/run_tests.ps1` currently passes 60 tests. Every gate contract field is
now resolved, so `config/milky_cow_contract_gate.json` reads
`contracts_resolved_integrated_sweep_still_blocked`. The sweep remains blocked
by work rather than by decisions, listed in `remaining_blockers_before_the_sweep`:
no study-scale runner exists, the ordering-sensitivity arm has not been run, and
the accumulation-trigger exclusion is a recommendation awaiting confirmation.

Measured tape baseline, useful for sizing every later result: one PA at 1 MNQ
taking every accepted opportunity nets a median $6,139 per 720-day window
(min -$1,430, max $21,024) and $27,683 across the whole 2,384-day tape.

Four recorded consequences to carry into reporting:

- the phase-1 no-slippage assumption is biased `favors_high_n`;
- high-N book fill is expected to be limited by Evaluation pipeline time, not
  by cash: a PA nets a median $6,139 per horizon while a new PA costs $160, so
  attribute any unfilled book explicitly rather than assuming capital;
- payout-day sit-outs do not blackout the book, but policies that reset
  accounts to a common balance can re-synchronize them, so the distribution of
  simultaneous sit-outs is a measured per-arm result; and
- a withdrawn-cash objective penalises `minimum_500_always`, which is the
  parent's own baseline policy, so the un-withdrawn companion belongs beside
  every ranking.
