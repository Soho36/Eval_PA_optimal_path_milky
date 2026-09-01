# Evidence

## Parent snapshot

This starter was assembled from:

- repository: `I:\PycharmProjects\Eval_PA_optimal_path`
- branch at assembly: `master`
- commit: `106cfb782c6e573856282095441bb69f23924a55`

`TRANSFER_MANIFEST.json` is the authoritative byte-level inventory of the
bundle. The copied upstream manifests preserve the earlier EODMAE and
Accounts_staggering source revisions. Verify all hashes before first use.

## Strong reusable evidence

- `data/raw/rr1/`: frozen completed-trade input tape.
- `manifests/rr1_import_20260829.json`: raw import identity.
- `manifests/upstream_evidence_20260829.json`: pinned upstream revisions.
- `rules/`: effective-dated Legacy 25K study rules and audit.
- `tests/fixtures/evaluation/eodmae_legacy_25k_x3_behavior_lock.json`:
  Evaluation behavior lock.
- `reference/RR_r_MFE_buy-stop-entry(EXAMPLE).cs`: explanation of the source
  strategy's one-open-trade signal blocking.

## Candidate evidence, not conclusions

- `config/payout_policies.json`: six policies to retest.
- files in `reference/shared_source/`: reviewed parent implementations that may
  be imported selectively with tests.
- files in `reference/shared_tests/`: parity and integrity test references.

## Deliberate exclusions

No staggering routing fixture, withdrawal compatibility fixture, inventory-grid
result, or parent optimum claim is part of this bundle.
