# Testing

Run from the repository root:

```powershell
.\scripts\run_tests.ps1
```

The runner prefers the actual `venv/`, disables bytecode writes, and propagates
the unittest exit code. `scripts/run_verified_tests.ps1` is the underlying
failure-propagating runner.

Current executable coverage (48 tests):

- immutable parent-transfer and acknowledged-deviation verification;
- reviewed-source/local-derivative SHA-256 provenance;
- RR1 manifest, row/stat parity, Tallinn DST fold/gap boundaries,
  12,658 -> 9,299/3,359 selection, accepted-stream digest, exact lifecycle
  stream/ordinal binding, zero-duration ordering, and membership records;
- 5,029 raw / 3,722 accepted path ambiguities, all three path scenarios, and a
  per-opportunity seeded-assignment digest;
- three pinned Evaluation episodes as upstream behavior locks;
- N=0/1/2/3 copy counts, strict activation, explicit compliance, correlated
  deaths, no bare raw offers, entry-state immutability, exact-exit one-shot
  settlement, and commission-timing divergence;
- scaling threshold inclusion, per-account/synchronized scope, sticky/immediate
  behavior, integer counts, causal decision time, and linear outcomes;
- pipeline-cap accounting, acquisition cadence, explicit death counts, no
  instant replacement PA, and target-overshoot prevention;
- external-capital literal validation, starting-cash priority, exact shortfall,
  cap exhaustion, irreversible first-PA closure, no partial funding, and ledger
  reconciliation;
- stateful Evaluation threshold, path-order, cycle-boundary, carry/reset, and
  renewal-preflight behavior;
- all six payout candidates, day/profit gates, payout 3/4 and 5/6 transitions,
  cent floors, trader split crossing, period reset, and no-mutation preflight;
- deterministic N=1 acquisition/payout/death/replacement and N=2 synchronized-
  copy/divergence lifecycle traces, including prior-batch settlement,
  due-exit precedence, sequential correlated-death replacement debt,
  death-before-growth priority, and payout/treasury rollback; and
- active gate governance, every PA count 1..20, and exact six payout candidates.

Still required before a study-scale integration: selected-policy fixtures for Evaluation,
scaling, acquisition/replacement, payout timing, capital, event order, objective,
rolling cohorts, regimes, and the remaining non-path stresses.
