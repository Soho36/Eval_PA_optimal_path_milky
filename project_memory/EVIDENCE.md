# Evidence

## Transfer snapshot

The starter was assembled from `I:\PycharmProjects\Eval_PA_optimal_path` at
revision `106cfb782c6e573856282095441bb69f23924a55`.

`TRANSFER_MANIFEST.json` is the immutable handoff inventory. The first-session
verification found all 73 imported parent artifacts exact. The user's shorter
`.gitignore` and deleted one-use prompt are recorded separately in
`manifests/transfer_verification_20260901.json`. Subsequent edits to named
starter-bundle files are project development, not imported-parent mutation.

`manifests/implementation_provenance_20260901.json` binds each reviewed parent
source and active local derivative by SHA-256. No local code file claims to be
an exact byte-for-byte code import.

## Strong reusable evidence

- `data/raw/rr1/`: frozen 12,658-row completed-trade tape.
- `manifests/rr1_import_20260829.json`: raw import identity.
- `rules/MILKY_COW_COPY_TO_ALL_RULES.txt`: active PA-book overlay.
- `config/milky_cow_contract_gate.json`: active foundation gate.
- `tests/fixtures/evaluation/eodmae_legacy_25k_x3_behavior_lock.json`:
  Evaluation-only upstream behavior lock.
- executable RR1, accepted-stream, copy-to-all, lifecycle, capital, and
  provenance fixtures under `tests/`.

The verified RR1 path-order population contains 5,029 raw ambiguous offers:
3,722 accepted and 1,307 blocked. Under seed 20260823, the accepted ambiguous
opportunities resolve 1,838 MAE-first / 1,884 MFE-first. The ordered
`trade_key + NUL + path_order + LF` assignment digest is
`fe8ffebb92966bfb40675100b7a56d5977c0cc1c40bfbe9d4e3aea2341bdda45`.
This proves reproducibility, not the real intratrade order.

The deterministic contract fixture now exercises N=1 acquisition, activation,
payout, death and non-instant replacement, plus N=2 copied trades followed by
activation/payout divergence. Its fixed one-MNQ, perfect-linear execution and
synthetic nonoverlapping offers are fixture assumptions, not study findings.

## Candidate evidence, not conclusions

- `config/payout_policies.json`: six policies to retest.
- inherited effective-dated rules outside the milky overlay.
- files in `reference/shared_source/` and `reference/shared_tests/`.
- copied cohort, regime, horizon, inventory, and policy-ranking claims.

## Evidence limitations

The ignored/untracked RR1 bytes are fully hashed, but their generator/MQL5
lineage is not proven. Aggregate identical execution at up to 20 copied and
scaled accounts is not established and requires an explicit assumption plus
stress.
