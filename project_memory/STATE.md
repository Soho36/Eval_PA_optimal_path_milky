# State

## Current status

Foundation contracts and fixtures are executable. No integrated lifecycle,
parameter sweep, result, optimum, or policy ranking exists.

Verified and implemented:

- 73/73 imported parent artifacts exact, with two user-confirmed starter
  deviations recorded separately;
- RR1 12,658 raw -> 9,299 accepted / 3,359 blocked and accepted-stream digest;
- Tallinn/DST normalization and three Evaluation behavior-lock episodes;
- copy-to-all parity for N=0..3, strict activation, compliance recording,
  correlated deaths, accepted-stream membership type, entry-state snapshot,
  and one-shot exact-exit settlement;
- explicit per-account/synchronized scaling primitives and boundary tests,
  with no schedule selected;
- pipeline-cap, acquisition, death-count-bounded replacement intent primitives;
- none/fixed-budget/through-first-PA capital primitives, starting cash,
  irreversible closure, no partial top-up, and ledger reconciliation;
- active gate coverage for every PA count 1..20 and the exact six payout
  candidates; and
- source/local implementation provenance verification.

`scripts/run_tests.ps1` currently passes 32 tests. The integrated sweep remains
prohibited by the null/unresolved fields in `config/milky_cow_contract_gate.json`.
