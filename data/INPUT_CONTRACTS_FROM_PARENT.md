# Legacy 25K upstream input contracts

Status: **core contracts frozen and implemented for baseline v1** as of
2026-08-29. The richer diagnostic-ledger fields identified below remain planned
validation work and are not silently claimed as present.

This document defines the frozen inputs and the user-selected phase adapters.
It does not promote any inherited candidate to an integrated optimum.

## One product, four independent controls

The only product is Apex Legacy 25K Rithmic. The data model must keep these
controls independent:

1. Evaluation position size in MNQ (candidate: 3 MNQ);
2. PA requested copies per signal, `R`;
3. number of PA drawdown containers, `K`, with separate live and tradable K;
4. treasury/payout policy.

No field for another account tier belongs in the initial configuration or
result comparison.

## Observed common RR=1 source set

Both upstream worktrees currently contain byte-identical copies of the 23
RR=1.00 window exports and 23 corresponding stats files. They are not tracked by
either pinned commit.

| Set | Files | Bytes | Deterministic manifest SHA-256 |
|---|---:|---:|---|
| `RR/*/*_1.00.csv` | 23 | 1,713,202 | `b6815a2fa31a384e0735082f42459f7d1919a31abb17257201f5a7c733913f20` |
| `RR_stats/*/*_1.00_stats.csv` | 23 | 12,186 | `fa6cc07a699cf7604d12e5a59d34d2b0ee0ab4d8487f6eb2d67ee342c1f82c4d` |
| combined selection | 46 | 1,725,388 | `1bf2f1c83fe96bf5b86653583f33f52c35631cf0ea561566e0dcb35756274f7e` |

The digest algorithm sorts POSIX relative paths and updates SHA-256 for each
file with `path`, NUL, the file's raw SHA-256 digest, NUL, decimal byte size, and
newline. The same digest was obtained under both
`I:/PycharmProjects/EODMAE/1_sweeps` and
`I:/PycharmProjects/Accounts_staggering/1_sweeps`.

This establishes byte identity, not origin at either Git revision. All 46 files
are now copied byte-for-byte to `data/raw/rr1/` and listed individually in
`manifests/rr1_import_20260829.json`. The importer also verifies all paired
trade/stats counts and net-P&L totals.

## Raw offer contract

Each headerless trade export has seven positional fields:

```text
ticket, entry_time, exit_time, mae, mfe, pnl, candle_range
```

The upstream meaning is one isolated-window RR=1.00 signal at one MNQ before
the external $1.05 round-turn commission. `mae`, `mfe`, and `pnl` are dollar
amounts for that one MNQ. `candle_range` is not commission. The stats companion
must identify at least `run_tag`, `risk_reward`, `trades`, and `net_profit` so a
tester-truncated pass can be rejected.

An imported raw row must retain its bytes and provenance. A processed row must
have the following explicit fields:

| Field | Contract |
|---|---|
| `trade_key` | globally unique stable key; at minimum source manifest ID + window + source row + ticket |
| `strategy_id` | fixed inherited RR strategy identifier; never inferred from filename alone |
| `window_id` | one of `1-2` through `23-24`, preserving the source directory label |
| `entry_at`, `exit_at` | timezone-aware instants; `entry_at <= exit_at` |
| `source_entry_label`, `source_exit_label` | unchanged naive labels for audit |
| `source_timezone_rule` | named, effective-dated conversion rule; cannot be `UNKNOWN` in a day-sensitive run |
| `gross_pnl_usd_per_mnq` | source P&L before configured execution costs |
| `mae_usd_per_mnq` | adverse whole-trade extreme, normally non-positive |
| `mfe_usd_per_mnq` | favorable whole-trade extreme, normally non-negative |
| `commission_usd_per_mnq` | explicit effective-dated/scenario value, not hidden in P&L |
| `net_pnl_usd_per_mnq` | deterministic gross minus commission and declared slippage |
| `intratrade_path_status` | known, MAE-first bound, MFE-first bound, or declared seeded resolution |
| `source_file_sha256`, `source_row`, `source_ticket` | immutable provenance |

Normalization must reject rather than coerce invalid numerics, timestamps,
duplicate keys, unknown windows, exit-before-entry rows, missing companion stats,
or unsupported rule/timezone intervals. The upstream behavior of converting bad
numbers to zero or dropping invalid timestamps is not accepted.

## Resolved phase opportunity contract

The same 12,658 raw offers are adapted differently upstream:

- EODMAE applies one global causal position slot per Evaluation/cohort. Its
  validation reports 9,299 accepted offers and 3,359 blocked offers. Routing is
  restarted at every 30-day account boundary.
- Accounts_staggering keeps all 12,658 isolated-window offers and routes
  concurrent offers across K PAs. The observed cross-window peak overlap is
  five, which is the sole basis of `K >= 5R`.

These are intentionally different phase adapters. The user selected the first
contract below for baseline v1.

Three materially different contracts are possible:

1. **selected baseline:** preserve upstream phase adapters: global one-position
   Evaluation, concurrent PA offers;
2. use the globally accepted opportunity set in both phases, which requires
   re-estimating the five-overlap capacity claim;
3. use concurrent offers in both phases, which requires re-estimating the
   3-MNQ Evaluation candidate.

The reason is operational: one Evaluation has one global slot, whereas the PA
book spreads otherwise concurrent window opportunities over distinct accounts.
The Evaluation `[entry,exit)` rule remains a fill-time proxy because the frozen
CSV lacks setup/order timestamps; it matches EODMAE behavior, not literal
pending-order parity.

The frozen tape contains two entries at 00:00, 11 exits in 00:00-00:59, 97
cross-date trades and seven fills outside their file's nominal setup hour.
Baseline v1 retains those completed fills as authoritative. Evaluation day
credit uses the entry Tallinn local date; PA realized P&L and payout-day credit
use the exit Tallinn local date. The declared 01:00-23:59 session clock controls
cohort and payout events; it is not used to delete already-completed source
fills. This exception is explicit because `entry_time` is a fill time.

## Deterministic ordering contract

For decisions at an entry timestamp, only causal keys may be used. Baseline v1
freezes `(entry_at, window_order, source_row, ticket)`. Exit time, P&L, MAE and
MFE are future information at entry.

Pinned Accounts_staggering sorts equal-entry offers using exit time before
window/source order. Baseline v1 instead uses the causal key
`(entry_at, window_order, source_row, ticket)`. Equal entry timestamps do not
occur on this tape, so aggregate parity is unaffected. Tallinn localization
chooses DST `fold=0` for an ambiguous autumn label and rejects nonexistent
spring-forward labels; no frozen label is ambiguous or nonexistent.

Event ordering also needs explicit rules for:

- exits at the same instant as entries;
- multiple exits at one timestamp;
- zero-duration trades;
- Evaluation billing/pass at a trade exit;
- PA activation, payout approval/removal, death and treasury actions at the same
  timestamp.

## Evaluation adapter contract

The Evaluation adapter consumes raw offers plus the verified study rules. Its
current outcome exposes status/pass time, fee events, accepted/blocked/boundary
counts, failure/carry counts, terminal state and an optional per-trade state
trace. A future fully materialized diagnostic ledger should additionally carry:

```text
evaluation_id, event_at, event_type, source_trade_key,
balance_before/after, live_peak_before/after, floor_before/after,
trading_day_id, trading_days_completed, position_size_mnq,
fee_amount, cash_ledger_id, failure/pass reason
```

It must expose one-position blocking and cross-boundary behavior rather than
freezing only the 9,299 continuously accepted rows. The pinned EODMAE endpoint
episode file is insufficient for mechanics-level diagnosis.

## PA routing adapter contract

Every signal requests exactly `R` one-MNQ copies. The current per-decision
record returns signal/time, requested and filled copies, ordered eligible and
selected IDs, K counts and rejection reason. A richer audit record should add
each candidate's pre-decision equity/floor/headroom/assignment count:

```text
signal_key, entry_at, requested_copies, filled_copies,
ordered_eligible_pa_ids, selected_pa_ids,
each pre-decision equity/floor/headroom/assigned_count,
live_K, tradable_K, busy_K, rejection reason
```

Pinned `max_headroom` seat selection is the candidate ordering:

```text
(-1 * (equity - liquidation_floor), assigned_count, monotonically_allocated_pa_id)
```

Only alive, tradable, non-busy PAs are eligible. Pinned interval capacity treats
positions as `[entry, exit)`, so an exit at T frees an existing PA for an entry
at T. A newly purchased replacement at T is not eligible at T. The integrated
model must replace the upstream instant-purchase abstraction with verified
Evaluation/pass/activation delays.

Changing K alone must not change requested copies. Reports must distinguish
target K, live K, tradable K, filled exposure and congestion loss.

## Rule and availability contracts

Firm rules and commercial offers are normally separate primary inputs. The
named baseline deliberately replaces real offer history with the
user-authorized half-open interval `[-infinity, +infinity)`: Legacy 25K can be
purchased at every simulated timestamp. That assumption is versioned and is not
a claim about historical availability.

The study rule config covers Evaluation, PA, payout and transition formulas and
explicitly labels omitted compliance events. A future historical-availability
sensitivity must separately provide dated offers, prices and provenance; an
`UNKNOWN` interval would invalidate that sensitivity, but it does not override
the perpetual-availability baseline.

## Import and run manifest contract

Every frozen input record must include:

```text
artifact_id, original absolute path, upstream project,
upstream Git revision, tracked/untracked status, Git blob when applicable,
SHA-256, bytes, copied_at, extraction command/filter,
schema version, observed time range, parent artifact/hash for derived files
```

A result manifest includes this repository's code revision/tree hash and dirty
state, rule/config/policy hashes and effective values, the frozen raw aggregate
digest and import-manifest hash, resolver seed, exact cohort starts, timezone
provider, event-ordering version, runtime identity, and integrity results. A
future historical-offer sensitivity must add its separate offer-timeline hash.

The evidence observed in this audit is catalogued in
`manifests/upstream_evidence_20260829.json`. Exact raw copies are frozen under
`data/raw/rr1/` and bound by `manifests/rr1_import_20260829.json`.
