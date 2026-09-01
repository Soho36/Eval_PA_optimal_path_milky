# Legacy 25K parity fixtures

Status: raw integrity, representative EODMAE behavior, core routing/PA/payout
rules and integrated cash paths now have executable tests. The remaining
fixtures below are validation work, not a gate that forbids implementation.

## Evidence labels

Two labels must never be conflated:

- **upstream behavior lock** reproduces a pinned/hashed inherited mechanic even
  when it is simplified or conflicts with the current study contract;
- **study-contract fixture** reproduces the explicit Legacy 25K baseline chosen
  in `rules/25k_legacy_rules.txt` and its machine config.

A study-contract fixture makes an assumption executable and reviewable. It does
not prove that assumption was an effective historical Apex rule. Code, tests,
manifests and generated results are stronger evidence than this description.

## Raw-tape integrity prerequisite

`manifests/rr1_import_20260829.json` binds all 23 trade and 23 stats files. The
loader and tests currently lock:

- 46 exact artifacts and no extras;
- 12,658 normalized offers;
- 9,299 globally accepted and 3,359 blocked fill-time offers;
- peak positive-duration overlap five;
- one zero-duration trade and unique entry timestamps;
- exact per-file stats totals;
- historical Tallinn winter/summer offsets; and
- rejection of an extra file, a same-size byte tamper and a nonexistent DST-gap
  wall time.

Known cross-date/out-of-session completed fills remain in the fixture by design.
The session clock does not filter the tape.

## Evaluation: EODMAE Legacy 25K x3 behavior lock

Source definition:
`fixtures/evaluation/eodmae_legacy_25k_x3_behavior_lock.json`.

Executable tests reproduce three representative 180-day episodes from pinned
EODMAE commit `c7a08f41f6434440500dbaef731acc14a4708442`:

1. `2020-01-02 01:00` passes `2020-02-06 06:30`, pays `$70`, accepts 144,
   blocks 46, has no drawdown failure and carries one live renewal.
2. `2020-01-03 01:00` passes `2020-04-07 11:30`, pays `$140`, accepts 241,
   blocks 84, has two drawdown failures and one carried renewal.
3. `2020-01-06 01:00` is censored at 180 days, pays `$210`, accepts 300,
   blocks 100, has five drawdown failures and one carried renewal.

This is a behavior lock for the inherited 3-MNQ candidate, not evidence that 3
MNQ is an integrated optimum. Evaluation uses EODMAE's deterministic `resolved`
extreme ordering and a global `[entry_at, exit_at)` busy interval.

The latter is only a fill-time proxy. The supplied MT5 example checks open
positions at new-bar setup time, but no setup/order timestamp exists in the
exports. Exact source-semantic parity cannot be asserted from these files.

## PA routing: capacity and max-headroom

Source definition:
`fixtures/routing/accounts_staggering_routing_behavior_lock.json` at pinned
Accounts_staggering commit `b676def567e85a2bde2dd556ee9d2ad2899659b1`.

Executable coverage currently locks:

- peak positive-duration overlap five on this exact tape;
- `max_headroom` ordering by headroom descending, assignments ascending and PA
  ID ascending; and
- strict rejection of a PA activated at the signal timestamp.

Thus `K >= 5R` remains an exact immortal-seat capacity candidate for this tape,
not a future overlap guarantee and not an economic optimum. The upstream cash
advantage remains excluded from the Legacy 25K golden because it used different
drawdown/payout economics and coupled seat count to exposure.

Still to port as executable upstream locks:

- R copies require R times interval depth;
- sufficient K gives equal exposure across causal policies;
- death/replacement/later reuse;
- cross-horizon capacity with unscored outcome;
- same-timestamp death clustering and one replacement; and
- chronological handling of unsorted input.

Also add per-decision ledgers for exit-at-entry, replacement-at-entry,
zero-duration and causal equal-entry ties.

## PA state and payout study fixtures

The executable study-contract tests cover:

- the 25K Legacy trailing floor freezing at +`$100`;
- MAE-first PA drawdown with closing net P&L accounting;
- minimum/profitable-day and balance/cap gating through payout choice;
- all six policy shapes;
- direct `$500 per $1,000` accumulator reduction and carry semantics;
- gross PA debit versus split-adjusted treasury receipt;
- the payout 3-to-4 Safety Net transition and `$25,100.01` post-rule floor; and
- removal of the `$1,500` cap from payout 6 onward.

Payout consistency, request review, denial and processing delay deliberately
have no fixture because they are out of scope. The baseline payout event is
atomic.

## Withdrawal: old account_farming behavior lock

Source definition:
`fixtures/withdrawal/account_farming_200_per_400_behavior_lock.json`.

This specification locks the old runner's ratchet, immediate cash and exposure
coupling under a mechanical drawdown substitution. It remains intentionally
firm-invalid and is not yet an executable test. A literal `$200` request is
below the study's `$500` minimum, every live seat receives later signals, and
the runner omits eligibility/caps/splits and account activation.

The published allocation-sweep aggregate must not become a Legacy 25K golden:
its recorded simulator hash does not match a pinned `account_farming.py`, its
withdrawal economics used a `$2,500` drawdown, and its comparisons changed
exposure with K.

The integrated successor compares `$500/$1,000`, `$500/$1,500`, `$500/$2,000`,
`$1,000/$2,000`, maximum eligible and minimum eligible. These are candidates,
not parity conclusions or optima.

## Integrated lifecycle fixtures

Executable end-to-end tests currently lock:

- first Evaluation purchase from external capital;
- bootstrap first activation;
- eight PA payout-period days producing an atomic `$500` receipt;
- payout-funded second Evaluation purchase and activation;
- exact fee, contribution and ending-cash reconciliation;
- renewal receiving same-timestamp payout cash before a new Evaluation purchase;
  and
- activation-at-entry being requested but unfilled.

The versioned causal order is PA exit, Evaluation pass, session-close payout,
Evaluation renewal, pending-obligation/new-purchase treasury phase, then PA
entry. Pending activation is retried before a new purchase.

## Remaining high-risk fixtures

- Failed and live Evaluation states on an exact renewal boundary.
- Unpaid post-bootstrap renewal and multiple pending activations competing for
  one payout receipt.
- PA drawdown threshold equality under alternative extreme orders.
- DST fall-fold labels and rolling cohort starts across DST transitions.
- Cross-date/out-of-session trade accounting and zero-duration exit processing.
- PA death before/pending payout and withdrawal-induced router reprioritization.
- Ledger reconciliation after every event and endpoint balance-ceiling versus
  policy-requestable separation.
- CLI single/rolling manifests, complete-horizon filtering and explicit
  right-censoring.

No fixture may be cited as proof that Legacy 25K x3, `K >= 5R`/max_headroom, or
any payout policy is an integrated optimum. That requires the rolling and stress
study in this repository.
