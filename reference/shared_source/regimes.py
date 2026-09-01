"""Regime partitioning of cohort starts, and per-regime result summaries.

A regime is a *reporting* partition of cohort start dates. It never reaches the
simulator and cannot change a cohort result. It exists because the 2026-08-30
study found the difference between start periods larger than the difference
between any two policies: on the first manifested 720-day run, cohorts starting
in 2020-2021 broke even 23 times out of 87 while cohorts starting in 2022-2024
broke even 57 times out of 110.

A pooled figure over both is a mixture whose value depends on how many cohorts
each period happened to contribute, which is a property of the sampling stride
rather than of the policy. Every summary therefore reports per regime first and
labels the pooled row as a mixture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import statistics
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class Regime:
    """A half-open [from_date, to_date) window of cohort start dates."""

    name: str
    from_date: date | None = None
    to_date: date | None = None

    def contains(self, start: date) -> bool:
        if self.from_date is not None and start < self.from_date:
            return False
        if self.to_date is not None and start >= self.to_date:
            return False
        return True


# The default split is the one the first 720-day study surfaced. It is a
# reporting convention, not a claim that a structural break occurred exactly at
# midnight on 2022-01-01.
DEFAULT_REGIMES: tuple[Regime, ...] = (
    Regime("2020-2021", None, date(2022, 1, 1)),
    Regime("2022-2024", date(2022, 1, 1), None),
)

POOLED_LABEL = "ALL (mixture)"


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def load_regimes(payload: Mapping[str, Any] | None) -> tuple[Regime, ...]:
    """Build regimes from a config block, validating that they partition time.

    The windows must be ordered, contiguous and unbounded at both ends, so that
    every cohort start falls in exactly one regime and none is silently dropped
    from a comparison.
    """

    if not payload:
        return DEFAULT_REGIMES
    rows = payload.get("windows")
    if not rows:
        return DEFAULT_REGIMES
    regimes = tuple(
        Regime(
            name=str(row["name"]),
            from_date=_as_date(row.get("from_date")),
            to_date=_as_date(row.get("to_date")),
        )
        for row in rows
    )
    names = [regime.name for regime in regimes]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate regime name")
    if POOLED_LABEL in names:
        raise ValueError(f"{POOLED_LABEL!r} is reserved for the pooled row")
    if regimes[0].from_date is not None or regimes[-1].to_date is not None:
        raise ValueError("Regimes must be unbounded at both ends")
    for earlier, later in zip(regimes, regimes[1:]):
        if earlier.to_date is None or earlier.to_date != later.from_date:
            raise ValueError(
                "Regimes must be contiguous: "
                f"{earlier.name} ends {earlier.to_date}, {later.name} starts "
                f"{later.from_date}"
            )
    return regimes


def label_start(start_at: str | datetime, regimes: Sequence[Regime]) -> str:
    """Return the regime name containing this cohort start."""

    moment = (
        datetime.fromisoformat(start_at) if isinstance(start_at, str) else start_at
    )
    for regime in regimes:
        if regime.contains(moment.date()):
            return regime.name
    raise ValueError(f"No regime contains cohort start {moment.isoformat()}")


def _percentile(values: Sequence[float], fraction: float) -> float:
    if len(values) < 2:
        return float(values[0]) if values else 0.0
    index = min(9, max(0, round(fraction * 10) - 1))
    return float(statistics.quantiles(values, n=10)[index])


def summarize(
    results: Iterable[Mapping[str, Any]], regimes: Sequence[Regime]
) -> list[dict[str, Any]]:
    """Return one summary row per (policy, regime), plus a pooled mixture row.

    Rows are ordered policy-major, regime-minor, with the pooled row last inside
    each policy so a reader meets the per-regime figures first.
    """

    rows = list(results)
    order: list[str] = []
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        policy = str(row["policy_id"])
        if policy not in grouped:
            grouped[policy] = []
            order.append(policy)
        grouped[policy].append(row)

    summary: list[dict[str, Any]] = []
    for policy in order:
        buckets: dict[str, list[Mapping[str, Any]]] = {
            regime.name: [] for regime in regimes
        }
        for row in grouped[policy]:
            buckets[label_start(row["start_at"], regimes)].append(row)
        for name, bucket in buckets.items():
            summary.append(_stats(policy, name, bucket, pooled=False))
        summary.append(_stats(policy, POOLED_LABEL, grouped[policy], pooled=True))
    return summary


def _stats(
    policy: str, regime: str, rows: Sequence[Mapping[str, Any]], *, pooled: bool
) -> dict[str, Any]:
    nets = [float(row["net_realized_cash_usd"]) for row in rows]
    breakeven = sum(1 for value in nets if value >= 0)
    stats: dict[str, Any] = {
        "policy_id": policy,
        "regime": regime,
        "is_pooled_mixture": pooled,
        "cohorts": len(rows),
        "total_net_realized_cash_usd": round(sum(nets), 2),
        "median_net_realized_cash_usd": round(statistics.median(nets), 2) if nets else 0.0,
        "p10_net_realized_cash_usd": round(_percentile(sorted(nets), 0.1), 2),
        "p90_net_realized_cash_usd": round(_percentile(sorted(nets), 0.9), 2),
        "breakeven_cohorts": breakeven,
        "breakeven_share": round(breakeven / len(rows), 4) if rows else 0.0,
        "gross_payouts_usd": round(sum(float(r["gross_payouts_usd"]) for r in rows), 2),
        "external_contributions_usd": round(
            sum(float(r["external_contributions_usd"]) for r in rows), 2
        ),
        "pa_births": sum(int(r["pa_births"]) for r in rows),
        "pa_deaths": sum(int(r["pa_deaths"]) for r in rows),
        "mean_fill_rate": round(
            statistics.mean(float(r["fill_rate"]) for r in rows), 4
        )
        if rows
        else 0.0,
        "cohorts_reaching_pa": sum(1 for r in rows if r.get("first_pa_at")),
        "cohorts_reaching_payout": sum(1 for r in rows if r.get("first_payout_at")),
    }
    if pooled:
        stats["warning"] = (
            "Pooled across regimes. Its value depends on how many cohorts each "
            "regime contributed, which is a property of the sampling stride. "
            "Do not rank policies on this row."
        )
    return stats


def render(summary: Sequence[Mapping[str, Any]]) -> str:
    """Render a summary as a fixed-width table for terminal output."""

    header = (
        f"{'policy':<24}{'regime':<16}{'n':>5}{'total':>12}{'median':>10}"
        f"{'p10':>9}{'p90':>10}{'breakeven':>11}{'fill':>7}"
    )
    lines = [header, "-" * len(header)]
    previous = None
    for row in summary:
        if previous is not None and row["policy_id"] != previous:
            lines.append("")
        previous = row["policy_id"]
        name = row["policy_id"] if row["regime"] != POOLED_LABEL else ""
        lines.append(
            f"{name[:23]:<24}{row['regime']:<16}{row['cohorts']:>5}"
            f"{row['total_net_realized_cash_usd']:>12,.0f}"
            f"{row['median_net_realized_cash_usd']:>10,.0f}"
            f"{row['p10_net_realized_cash_usd']:>9,.0f}"
            f"{row['p90_net_realized_cash_usd']:>10,.0f}"
            f"{row['breakeven_cohorts']:>7}/{row['cohorts']:<3}"
            f"{row['mean_fill_rate']:>7.3f}"
        )
    lines.append("")
    lines.append(
        "Net realized cash = ending treasury cash minus external contributions. "
        "The pooled row is a mixture; rank on the per-regime rows."
    )
    return "\n".join(lines)
