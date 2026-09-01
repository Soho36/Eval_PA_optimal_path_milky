# Testing

Run from the repository root:

```powershell
.\scripts\run_tests.ps1
```

The initial tests lock only the project boundary: copy-to-all distribution,
absence of staggering/routing/dormant roles, PA-count coverage through 20, and
the presence of unresolved sweep blockers.

Before an integrated sweep, add executable tests for:

- raw RR1 manifest verification and Tallinn timestamps;
- pinned Evaluation parity;
- N eligible PAs producing exactly N account-level copies;
- activation-at-entry exclusion;
- independent account balances/payout histories;
- correlated outcomes before account states diverge;
- deaths and replacements;
- each contract-scaling threshold and its timing;
- payout boundaries and treasury reconciliation; and
- deterministic CLI output/provenance.
