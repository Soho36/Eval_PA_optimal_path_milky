"""Parameter sweep over the N x payout-policy grid.

One arm is one (N, payout policy, path arm, event order). An arm is executed by
running every complete monthly cohort through ``run_cohort`` and aggregating
the per-cohort results. Arms are independent, so they parallelise cleanly and
the aggregate is order-independent: the same grid always produces the same
digest regardless of scheduling.

This module aggregates. It does not rank policies or draw conclusions; the
gate's remaining blockers still stand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import statistics as stats
from typing import Any, Iterable, Sequence

from .cohorts import CohortWindow, first_session_monthly_cohorts
from .inputs import VerifiedRR1Dataset, load_verified_rr1_dataset, money
from .policy_bundle import load_policy_bundle
from .study_runner import CohortResult, run_cohort


def _quantile(sorted_values: Sequence[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return money(
        sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    )


@dataclass(frozen=True, slots=True)
class ArmSummary:
    """One (N, payout policy) arm aggregated across every complete cohort."""

    arm_id: str
    target_active_pas: int
    payout_policy_id: str
    path_stress_arm: str
    event_order_mode: str
    execution_model_id: str
    cohort_count: int

    retained_median_usd: float
    retained_p25_usd: float
    retained_p75_usd: float
    retained_min_usd: float
    retained_max_usd: float
    retained_total_usd: float
    positive_cohorts: int

    harvest_median_usd: float
    harvest_max_usd: float
    harvest_total_usd: float

    pas_activated: int
    pa_deaths: int
    correlated_death_events: int
    max_simultaneous_deaths: int
    cohorts_with_a_survivor: int

    payouts_executed: int
    payouts_deferred_open_copy: int
    unwithdrawn_equity_total_usd: float
    horizon_open_batches: int

    cash_bound_days: float
    pipeline_bound_days: float
    book_full_days: float
    growth_ready_days: float
    dormant_slot_days: float

    def as_row(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "n": self.target_active_pas,
            "payout_policy_id": self.payout_policy_id,
            "path_stress_arm": self.path_stress_arm,
            "event_order_mode": self.event_order_mode,
            "execution_model_id": self.execution_model_id,
            "cohort_count": self.cohort_count,
            "owner_net_retained_cash_usd": {
                "median": self.retained_median_usd,
                "p25": self.retained_p25_usd,
                "p75": self.retained_p75_usd,
                "min": self.retained_min_usd,
                "max": self.retained_max_usd,
                "total": self.retained_total_usd,
                "positive_cohorts": self.positive_cohorts,
            },
            "cumulative_payout_harvest_usd": {
                "median": self.harvest_median_usd,
                "max": self.harvest_max_usd,
                "total": self.harvest_total_usd,
            },
            "book": {
                "pas_activated": self.pas_activated,
                "pa_deaths": self.pa_deaths,
                "correlated_death_events": self.correlated_death_events,
                "max_simultaneous_deaths": self.max_simultaneous_deaths,
                "cohorts_with_a_survivor": self.cohorts_with_a_survivor,
            },
            "payouts": {
                "executed": self.payouts_executed,
                "deferred_open_copy": self.payouts_deferred_open_copy,
            },
            "right_censoring": {
                "unwithdrawn_equity_total_usd": self.unwithdrawn_equity_total_usd,
                "horizon_open_batches": self.horizon_open_batches,
                "note": "never summed into the headline metric",
            },
            "constraint_time_days": {
                "cash_bound": self.cash_bound_days,
                "pipeline_bound": self.pipeline_bound_days,
                "book_full": self.book_full_days,
                "growth_ready": self.growth_ready_days,
                "dormant_slot": self.dormant_slot_days,
            },
        }


def summarize_arm(results: Sequence[CohortResult]) -> ArmSummary:
    if not results:
        raise ValueError("An arm summary requires at least one cohort result")
    first = results[0]
    retained = sorted(row.owner_net_retained_cash_usd for row in results)
    harvest = sorted(row.cumulative_payout_harvest_usd for row in results)
    return ArmSummary(
        arm_id=first.arm_id,
        target_active_pas=first.target_active_pas,
        payout_policy_id=first.payout_policy_id,
        path_stress_arm=first.path_stress_arm,
        event_order_mode=first.event_order_mode,
        execution_model_id=first.execution_model_id,
        cohort_count=len(results),
        retained_median_usd=money(stats.median(retained)),
        retained_p25_usd=_quantile(retained, 0.25),
        retained_p75_usd=_quantile(retained, 0.75),
        retained_min_usd=money(retained[0]),
        retained_max_usd=money(retained[-1]),
        retained_total_usd=money(sum(retained)),
        positive_cohorts=sum(1 for value in retained if value > 0),
        harvest_median_usd=money(stats.median(harvest)),
        harvest_max_usd=money(harvest[-1]),
        harvest_total_usd=money(sum(harvest)),
        pas_activated=sum(row.pas_activated for row in results),
        pa_deaths=sum(row.pa_deaths for row in results),
        correlated_death_events=sum(row.correlated_death_events for row in results),
        max_simultaneous_deaths=max(row.max_simultaneous_deaths for row in results),
        cohorts_with_a_survivor=sum(1 for row in results if row.surviving_pa_count),
        payouts_executed=sum(row.payouts_executed for row in results),
        payouts_deferred_open_copy=sum(
            row.payouts_deferred_open_copy for row in results
        ),
        unwithdrawn_equity_total_usd=money(
            sum(row.surviving_unwithdrawn_equity_usd for row in results)
        ),
        horizon_open_batches=sum(row.horizon_open_batches for row in results),
        cash_bound_days=round(sum(row.cash_bound_days for row in results), 2),
        pipeline_bound_days=round(sum(row.pipeline_bound_days for row in results), 2),
        book_full_days=round(sum(row.book_full_days for row in results), 2),
        growth_ready_days=round(sum(row.growth_ready_days for row in results), 2),
        dormant_slot_days=round(sum(row.dormant_slot_days for row in results), 2),
    )


def run_arm(
    root: str | Path,
    dataset: VerifiedRR1Dataset,
    cohorts: Sequence[CohortWindow],
    *,
    target_active_pas: int,
    payout_policy_id: str,
    path_stress_arm: str | None = None,
    event_order_mode: str | None = None,
    execution_model_id: str | None = None,
    exploratory: bool = False,
) -> tuple[ArmSummary, list[CohortResult]]:
    """Execute one arm across every supplied cohort."""

    bundle = load_policy_bundle(
        root,
        target_active_pas=target_active_pas,
        payout_policy_id=payout_policy_id,
        path_stress_arm=path_stress_arm,
        event_order_mode=event_order_mode,
        execution_model_id=execution_model_id,
        exploratory=exploratory,
    )
    results = [run_cohort(bundle, dataset, cohort) for cohort in cohorts]
    return summarize_arm(results), results


# -- parallel execution -------------------------------------------------------
# Arms are independent, so a worker holds one dataset and one cohort list for
# its whole life and each task is a self-contained arm.

_WORKER: dict[str, Any] = {}


def init_worker(root: str, horizon_days: int) -> None:
    root_path = Path(root)
    dataset = load_verified_rr1_dataset(root_path / "data" / "raw" / "rr1")
    _WORKER["root"] = root_path
    _WORKER["dataset"] = dataset
    _WORKER["cohorts"] = first_session_monthly_cohorts(
        dataset.selection.accepted_opportunities, horizon_days=horizon_days
    ).cohorts


def run_arm_task(task: tuple[int, str, str, str, str, bool]) -> dict[str, Any]:
    """Worker entry point: one arm, returned as plain data."""

    (
        target_active_pas,
        payout_policy_id,
        path_stress_arm,
        event_order_mode,
        execution_model_id,
        exploratory,
    ) = task
    summary, results = run_arm(
        _WORKER["root"],
        _WORKER["dataset"],
        _WORKER["cohorts"],
        target_active_pas=target_active_pas,
        payout_policy_id=payout_policy_id,
        path_stress_arm=path_stress_arm,
        event_order_mode=event_order_mode,
        execution_model_id=execution_model_id,
        exploratory=exploratory,
    )
    return {
        "summary": summary.as_row(),
        "cohorts": [
            {
                "n": row.target_active_pas,
                "payout_policy_id": row.payout_policy_id,
                "path_stress_arm": row.path_stress_arm,
                "event_order_mode": row.event_order_mode,
                "execution_model_id": row.execution_model_id,
                "start_at": row.start_at.isoformat(),
                "horizon_end_at": row.horizon_end_at.isoformat(),
                # Reconciliation: retained == ending_cash - owner_capital, and
                # for a reconciled ledger also harvest - fees.
                "retained_usd": row.owner_net_retained_cash_usd,
                "owner_capital_usd": row.owner_capital_supplied_usd,
                "ending_cash_usd": row.ending_cash_usd,
                "fees_paid_usd": row.fees_paid_usd,
                "harvest_usd": row.cumulative_payout_harvest_usd,
                "unwithdrawn_usd": row.surviving_unwithdrawn_equity_usd,
                "evaluations_purchased": row.evaluations_purchased,
                "renewals_paid": row.evaluation_renewals_paid,
                "renewals_unfunded": row.evaluation_renewals_unfunded,
                "activated": row.pas_activated,
                "deaths": row.pa_deaths,
                "correlated_death_events": row.correlated_death_events,
                "max_simultaneous_deaths": row.max_simultaneous_deaths,
                "survivors": row.surviving_pa_count,
                "payouts": row.payouts_executed,
                "payouts_deferred": row.payouts_deferred_open_copy,
                "first_pa_activated_at": (
                    row.first_pa_activated_at.isoformat()
                    if row.first_pa_activated_at
                    else ""
                ),
                # Constraint attribution: which limit actually bound.
                "cash_bound_days": row.cash_bound_days,
                "pipeline_bound_days": row.pipeline_bound_days,
                "book_full_days": row.book_full_days,
                "growth_ready_days": row.growth_ready_days,
                "dormant_slot_days": row.dormant_slot_days,
                "horizon_open_batches": row.horizon_open_batches,
            }
            for row in results
        ],
    }


def build_grid(
    n_values: Iterable[int],
    payout_policy_ids: Iterable[str],
    *,
    path_stress_arm: str,
    event_order_mode: str,
    execution_model_ids: Sequence[str],
    exploratory: bool = False,
) -> list[tuple[int, str, str, str, str, bool]]:
    """The full product, including execution: two models are two arms."""

    return [
        (n, policy_id, path_stress_arm, event_order_mode, model_id, exploratory)
        for n in n_values
        for policy_id in payout_policy_ids
        for model_id in execution_model_ids
    ]
