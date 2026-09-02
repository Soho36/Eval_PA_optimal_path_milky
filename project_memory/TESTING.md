# Testing

Run from the repository root:

```powershell
.\scripts\run_tests.ps1
```

The runner prefers the actual `venv/`, disables bytecode writes, and propagates
the unittest exit code. `scripts/run_verified_tests.ps1` is the underlying
failure-propagating runner.

Current executable coverage (68 tests):

- immutable parent-transfer and acknowledged-deviation verification;
- reviewed-source/local-derivative SHA-256 provenance;
- RR1 manifest, row/stat parity, Tallinn DST fold/gap boundaries,
  12,658 -> 9,299/3,359 selection, one-time accepted-stream digest/record cache,
  exact lifecycle stream/ordinal binding, zero-duration ordering, and membership
  records;
- deterministic monthly sessions and complete-horizon filtering: 55 of 79
  represented months are fully observed at 720 days;
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
  reconciliation, plus owner-capital, retained-cash and payout-harvest
  identities;
- stateful Evaluation threshold, path-order, cycle-boundary, carry/reset, and
  renewal-preflight behavior;
- all six payout candidates, day/profit gates, payout 3/4 and 5/6 transitions,
  cent floors, trader split crossing, period reset, exact 23:59 timing, and no
  mutation when preflight or payout-record construction fails;
- deterministic N=1 acquisition/payout/death/replacement and N=2 synchronized-
  copy/divergence lifecycle traces, including prior-batch settlement,
  due-exit precedence, sequential correlated-death replacement debt,
  death-before-growth priority, unfunded-renewal capacity release, retryable
  unfunded replacement backlog, one purchase decision per timestamp, and
  payout/treasury rollback; and
- active gate governance, every PA count 1..20, and exact six payout candidates.

Still required before study-scale integration:

- the per-Evaluation cycle-local consumer and gate-to-runtime policy bundle;
- answers to the four open funding/objective/order/horizon questions;
- one real-tape N=1 result manifest and the study runner;
- a configurable deterministic order-sensitivity arm; and
- the one-tick-per-side full-N execution-cost sensitivity.
