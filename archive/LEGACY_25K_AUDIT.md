# Legacy 25K rule audit

Audit date: 2026-08-29 (Europe/Tallinn).

Scope: Apex Legacy 25K Rithmic Evaluation, resulting Legacy 25K PA, and
payout/reinvestment mechanics only. No value, example, calculation, or result
for another account size or platform is a model input.

## Revised verdict

**READY FOR BASELINE IMPLEMENTATION AS A COUNTERFACTUAL STUDY.**

The user has resolved the material rule choices needed for the first model. The
primary specification is now `rules/25k_legacy_rules.txt`; machine-readable
parameters and the six payout candidates are in:

- `config/legacy_25k_baseline.json`
- `config/payout_policies.json`

This does not turn the supplied text into dated historical evidence. Instead,
the model has an explicit, reproducible scenario: Legacy 25K is perpetually
available, a one-day promotion applies throughout, selected official-rule gaps
are represented by named study assumptions, and intentionally omitted
compliance/processing events do not invalidate the baseline.

Implementation is authorized. The RR=1 tape has now been frozen locally with an
individual-file import manifest, and the phase contracts and behavior-lock
fixtures are defined. Candidate comparisons still require this repository's
tests and run manifests before any result can be called an integrated optimum.

## Source record and evidence status

| Local source | Bytes | SHA-256 | Role |
|---|---:|---|---|
| `EV-account_rules.txt` | 7,055 | `8256ad5467f3e9b5b36b1f4ef8aa6ec684f62ef33497fd7cbbacf3994438fb7a` | undated supporting excerpt |
| `Payout_rules.txt` | 7,984 | `3ea26951c053655639c87189882cfdec7c79278934b9dfa216fb542c9a0c6632` | undated supporting excerpt |
| `RR_r_MFE_buy-stop-entry(EXAMPLE).cs` | 26,369 | `7509483ffa61581680347ef6bc5e812b46d0308e16551b82abb282faaaccd48c` | tracked MQL5 semantic example at local commit `0ac561ae7990da7031241180f6ec545b94075ca9`; not proven generator of the frozen CSVs |

The wording closely matches the following live official pages checked on
2026-08-29, but they are not archived effective-date evidence:

- [Legacy Evaluation Rules](https://apextraderfunding.com/help-center/legacy-evaluation-accounts/legacy-evaluation-rules/)
- [Legacy PA Payout Parameters](https://apextraderfunding.com/help-center/legacy-payouts/legacy-pa-payout-parameters/)
- [Legacy Performance Account Compliance](https://apextraderfunding.com/help-center/performance-accounts-pa/legacy-performance-account-pa-compliance/)
- [Legacy PA activation](https://apextraderfunding.com/help-center/legacy-evaluation-accounts/how-to-activate-your-legacy-pa/)
- [Legacy Products Overview](https://apextraderfunding.com/help-center/legacy-products/legacy-products-overview/)
- [Payout Method Information](https://apextraderfunding.com/help-center/performance-accounts-pa/payout-method-information/)

The baseline is not a historical-availability reconstruction, so lack of an
archived offer interval is no longer a blocker. Every result must identify the
study rule version and must not be presented as exact historical Apex behavior.

## Resolved audit items

| Former issue | Baseline resolution | Status |
|---|---|---|
| Legacy retirement/offer history | Treat new Legacy 25K Evaluations as available for purchase at all simulated timestamps. | user study assumption |
| Starting state | Rolling historical cohorts; each starts with zero Evaluations/PAs and buys one Evaluation at cohort start. | user study assumption |
| Pre-first-PA funding | Seed one purchase fee; ledger minimum just-in-time external shortfalls for scheduled Evaluation renewals and first PA activation until that PA exists. | user study assumption |
| Existing subscriptions | Excluded from the main study; may be a later scenario. | deferred |
| Evaluation trading days | Assume a one-day promotion throughout the baseline. | user study assumption |
| Phase opportunity mismatch | Evaluation uses one global position slot; PA retains all concurrent cross-window offers. | user-confirmed phase contract |
| Timestamp timezone | Europe/Tallinn with IANA historical DST; 01:00 open and 23:59 close; ambiguous labels use fold=0 and nonexistent labels fail validation. | user study assumption |
| MQL5 clock conflict | The example declares no timezone and defaults flattening to 23:30. It does not override the user-selected Tallinn 01:00/23:59 convention. | resolved in favor of explicit study assumption |
| Tape/session exceptions | Retain 2 authoritative 00:00 entries, 11 exits during 00:00-00:59, and 97 cross-date trades; session hours govern model events rather than filtering fills. Evaluation day uses entry date; PA P&L day uses exit date. | user study/data contract |
| Drawdown equality | Equity touching the threshold fails (`<=`). | conservative upstream compatibility assumption |
| Evaluation drawdown freeze | Disabled to retain the stricter pinned EODMAE behavior; configurable sensitivity. | upstream compatibility assumption |
| Evaluation-to-PA delay | Charge activation and create the PA immediately at the passing trade exit. | upstream compatibility assumption |
| PA position scaling | One MNQ per selected PA; scaling limit is nonbinding. | user-confirmed strategy scope |
| PA account-count cap | No separate firm-wide ownership/activation cap is imposed; K is the study variable. Add a named cap sensitivity if evidence is supplied. | study assumption due absent rule in supplied excerpts |
| Risk/reward | Fixed 1:1 strategy is within the stated 5:1 maximum. | nonbinding |
| DCA/adding/hedging/variable size | Inapplicable unless completed-trade evidence contradicts the fixed strategy contract. | out of scope |
| PA 30% MAE guideline | Do not model it in the first study. | out of scope |
| Payout consistency | Do not model the 30% consistency rule in the first study. | out of scope |
| Payout processing | Valid requests approve, remove balance, and reach treasury atomically; no delays or denials. | study simplification |
| Old `$200/$400` action | Replace with an executable `$500/$1,000` 50% analogue and compare five additional requested policies. | resolved candidate set |

## Product and Evaluation contract

The baseline is Legacy 25K Rithmic only:

- USD 25,000 start, USD 1,500 target, USD 1,500 trailing drawdown;
- no daily loss limit;
- 3 MNQ Evaluation size, retained as an inherited candidate rather than a
  proven integrated optimum;
- USD 35 purchase/renewal and USD 125 activation snapshot from pinned EODMAE;
- fixed 30-calendar-day renewal boundaries with live-state carry, failed-state
  renewal/reset, and exit/pass/failure processed before an exact boundary;
- trailing-threshold touch is failure and Evaluation threshold freeze is off;
- pass at realized net balance >= USD 26,500 after one modeled trading day;
- immediate paid activation at the passing exit, with the new PA first eligible
  for signal entries strictly after that timestamp.

The fee amounts and renewal mechanics remain configurable upstream-compatibility
assumptions. They are sufficient to implement a baseline and should later receive
price/cycle sensitivity tests; they do not reopen account-type selection.

## Opportunity-set contract

The difference between the two upstream trade counts is intentional and now
specified by phase.

### Evaluation

Replay the 23 windows as one causal stream per Evaluation cycle. A completed
trade occupies the global slot over `[entry_at, exit_at)`. Offers whose entries
occur while that slot is occupied are blocked for that Evaluation. This is a
filled-position-time proxy for the source strategy behavior; no pending-order or
broker-fill engine is introduced.

The supplied example is MQL5 despite its `.cs` suffix. At each new setup bar it
returns when `PositionsTotal() > 0`; the export, however, contains only fill and
exit timestamps. It has no setup/order timestamp with which to reconstruct that
decision. The adapter is therefore exact parity with pinned EODMAE behavior but
only semantic evidence for the underlying EA. The example is not cryptographically
established as the generator of the frozen headerless exports; unlike those
files, the example's writer emits a header. It also declares no timezone and
defaults its flatten input to 23:30, so it is not evidence for the study's
Tallinn 01:00/23:59 session convention.

The pinned EODMAE validation observed 12,658 raw offers, 9,299 accepted offers,
and 3,359 blocked offers under its global adapter. Those counts remain a parity
target, not a hard-coded input filter: each Evaluation and renewal cycle must
perform its own causal replay.

### PA book

Retain all 12,658 concurrent cross-window opportunities and route fixed R copies
across K PAs. Each selected PA receives one MNQ. `max_headroom` remains the
candidate router with the pinned tie-breaks. `K >= 5R` is an observed historical
capacity candidate on this tape, not a guarantee and not yet an integrated
optimum.

This contract explains why Evaluation and PA trade counts differ and prevents a
false parity demand between phases.

## Time contract

Treat naive source labels as Europe/Tallinn local time and attach the IANA zone,
including historical DST changes. The modeled session is 01:00 through 23:59 on
the same local date; that date is the trading-day ID. Exit at T frees an existing
slot before entry at T.

For an ambiguous autumn-fold label, choose `fold=0`; reject a nonexistent
spring-gap label. The completed tape is authoritative even when a fill lies
outside 01:00-23:59 or crosses a local calendar boundary: both 00:00 entries,
the 11 exits during 00:00-00:59, and all 97 cross-date trades are retained.
Session hours schedule cohort and payout events; they do not filter completed
trades. Evaluation day credit follows entry local date, while PA realized
P&L/profitable-day credit follows exit local date.

This is the authoritative study mapping. It deliberately does not reconstruct
the firm's Eastern-Time holiday calendar, so results describe the supplied
strategy tape under its native session convention.

## PA contract and excluded compliance

The baseline PA starts at USD 25,000, trails USD 1,500 below modeled peak equity,
and freezes its liquidation threshold at USD 25,100. Threshold touch kills the
PA. A failed PA has no reset.

R and K remain independent: baseline R is one requested one-MNQ copy; K is a
policy variable. A K comparison that silently increases requested copies is
invalid. The baseline imposes no additional firm-wide PA count cap because the
supplied excerpts do not define one; any cap is a named sensitivity, not an
unstated constraint.

The first study creates no state transition from the 30% MAE guideline. DCA,
adding, hedging, and variable sizing are recorded as inapplicable to the fixed
strategy. If the completed-trade data contradicts that contract,
the affected run must fail validation rather than silently ignore it.

## Payout contract

The baseline retains the following per-PA eligibility and caps from the supplied
excerpt:

- eight trading days since activation or last executed request;
- at least five days with realized net profit >= USD 50;
- request-gate balance of USD 26,600;
- USD 500 minimum request;
- USD 1,500 maximum for executed payouts 1 through 5 and no fixed dollar cap
  from payout 6 onward;
- 100% trader share of the first USD 25,000 cumulative gross payouts per PA and
  90% thereafter.

The supplied text is ambiguous about balance semantics after the third payout.
That ambiguity is now a configurable baseline assumption rather than a blocker:

- payouts 1-3 balance-allowed maximum =
  `500 + max(0, balance - 26,600)`;
- payout 4 onward balance-allowed maximum =
  `max(0, balance - 25,100.01)`, leaving one cent above the threshold because
  threshold touch fails;
- apply the payout-number dollar cap after the balance formula;
- the USD 26,600 request gate still applies to every payout opportunity.

The 30% payout consistency calculation is omitted. Request, approval, balance
removal, and treasury receipt are atomic, with no denial or delay state. These
choices simplify the first economic comparison and must be visible in every run
manifest.

## Executable payout-policy candidates

The integrated comparison contains exactly six policies:

1. `$500 per $1,000` accumulated eligible incremental profit — direct 50%
   analogue of the old `$200/$400` idea;
2. `$500 per $1,500`;
3. `$500 per $2,000`;
4. `$1,000 per $2,000`;
5. maximum eligible withdrawal whenever eligible;
6. minimum-only USD 500 payout whenever eligible.

The threshold policies require both their full profit trigger and eligibility
for their full request amount. Realized net losses reduce the per-PA accumulator,
which is floored at zero. On execution, the trigger is subtracted and excess
accumulation carries forward.

The old account_farming `$200/$400` result remains a behavior-lock fixture only.
It used immediate USD 200 removal, abstract PA purchases, and exposure that grew
with K. It is not a golden for any policy above.

## Remaining validation work that does not block coding

The rules and input-contract gates are closed for this named baseline. The raw
23 trade and 23 stats files are frozen under `data/raw/rr1/`; their individual
hashes and combined digest are recorded in
`manifests/rr1_import_20260829.json`. Remaining obligations are to:

- retain manifest verification on every load and generated run;
- preserve the documented fill-time limitation rather than claiming exact EA
  setup/order parity;
- keep the independent EODMAE, routing, and old-withdrawal behavior locks green;
- keep rule fixtures for one-day pass, threshold touch, immediate activation,
  PA threshold freeze, payout eligibility/caps, and all six payout amount rules
  green, extending boundary cases as implementation grows;
- preserve deterministic same-timestamp ordering and verify every cash event
  against the treasury conservation identity;
- compare policies at fixed requested R and report delivered exposure;
- sensitivity-test no Evaluation freeze, fees/cycle, execution costs, payout
  balance formula, and atomic payout timing.

These are validation obligations, not reasons to substitute another account
type or to stop baseline implementation.

## Interpretation guardrail

Legacy 25K x3, `K >= 5R`/`max_headroom`, and `$500/$1,000` enter the integrated
study with different evidence strengths. They are candidates. Only reproducible
fixed-R comparisons under this common rule contract can support an integrated
recommendation, and robustness/holdout work is still required before using the
word "optimal."
