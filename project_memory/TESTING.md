# Testing

Run from the repository root:

```powershell
.\scripts\run_tests.ps1
```

The runner prefers the actual `venv/`, disables bytecode writes, and propagates
the unittest exit code. `scripts/run_verified_tests.ps1` is the underlying
failure-propagating runner.

Current executable coverage (32 tests):

- immutable parent-transfer and acknowledged-deviation verification;
- reviewed-source/local-derivative SHA-256 provenance;
- RR1 manifest, row/stat parity, Tallinn DST, 12,658 -> 9,299/3,359 selection,
  accepted-stream digest and membership records;
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
  reconciliation; and
- active gate governance, every PA count 1..20, and exact six payout candidates.

Still required before integration: selected-policy fixtures for Evaluation,
scaling, acquisition/replacement, payout timing, capital, event order, objective,
rolling cohorts, regimes, and stresses, followed by a tiny deterministic end-to-
end lifecycle fixture.
