"""Executable policy primitives that do not select an integrated baseline.

Implementation provenance:
- reviewed parent repository at revision
  106cfb782c6e573856282095441bb69f23924a55
- reference/shared_source/rules.py SHA-256
  f3924f349ef88f0b79803d001cb37e790c19624b243f07ffdd7525a7c6c68253

These are selective project contracts. Parent routing, inventory, and optimum
claims are intentionally absent.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Mapping


ScalingScope = Literal["per_account", "synchronized_book"]
ThresholdOperator = Literal["greater_than_or_equal", "greater_than"]
DownscaleRule = Literal["immediate", "sticky_max"]
SynchronizedAggregation = Literal["minimum_eligible_metric"]
ScalingDecisionTime = Literal[
    "entry_before_trade_after_prior_same_timestamp_events"
]
PurchaseReason = Literal["growth", "death_replacement"]
PipelineTargetAccounting = Literal["active_plus_running_and_pending"]


@dataclass(frozen=True, slots=True)
class ScalingLevel:
    minimum_metric_usd: float | None
    mnq: int

    def __post_init__(self) -> None:
        if self.minimum_metric_usd is not None and (
            not isinstance(self.minimum_metric_usd, (int, float))
            or isinstance(self.minimum_metric_usd, bool)
            or not math.isfinite(self.minimum_metric_usd)
        ):
            raise ValueError("Scaling threshold must be finite and numeric")
        if (
            not isinstance(self.mnq, int)
            or isinstance(self.mnq, bool)
            or self.mnq <= 0
        ):
            raise ValueError("Scaling MNQ count must be a positive integer")


@dataclass(frozen=True, slots=True)
class ScalingSchedule:
    """A complete entry-time MNQ schedule.

    The first level must use None as its lower bound so every possible account
    state has an explicit initial size. No policy is instantiated by default;
    the integrated config must supply every field.
    """

    policy_id: str
    scope: ScalingScope
    threshold_metric: str
    levels: tuple[ScalingLevel, ...]
    threshold_operator: ThresholdOperator
    decision_time: ScalingDecisionTime
    downscale_rule: DownscaleRule
    synchronized_aggregation: SynchronizedAggregation | None
    maximum_mnq: int
    outcome_scaling: Literal["linear_per_mnq"]

    def __post_init__(self) -> None:
        if self.scope not in {"per_account", "synchronized_book"}:
            raise ValueError("Unsupported scaling scope")
        if self.threshold_operator not in {
            "greater_than_or_equal",
            "greater_than",
        }:
            raise ValueError("Unsupported scaling threshold operator")
        if self.downscale_rule not in {"immediate", "sticky_max"}:
            raise ValueError("Unsupported scaling downscale rule")
        if self.outcome_scaling != "linear_per_mnq":
            raise ValueError("Unsupported scaling outcome rule")
        if (
            not isinstance(self.maximum_mnq, int)
            or isinstance(self.maximum_mnq, bool)
            or self.maximum_mnq <= 0
        ):
            raise ValueError("maximum_mnq must be a positive integer")
        if not self.policy_id:
            raise ValueError("Scaling policy identity is required")
        if self.threshold_metric not in {"realized_balance_usd", "equity_profit_usd"}:
            raise ValueError("Unsupported scaling threshold metric")
        if self.decision_time != "entry_before_trade_after_prior_same_timestamp_events":
            raise ValueError("Unsupported or non-causal scaling decision time")
        if (
            not isinstance(self.levels, tuple)
            or not self.levels
            or any(not isinstance(level, ScalingLevel) for level in self.levels)
            or self.levels[0].minimum_metric_usd is not None
        ):
            raise ValueError("First scaling level must be an unbounded base level")
        thresholds = [level.minimum_metric_usd for level in self.levels[1:]]
        if any(value is None for value in thresholds):
            raise ValueError("Only the first scaling level may be unbounded")
        numeric = [float(value) for value in thresholds]
        if numeric != sorted(numeric) or len(numeric) != len(set(numeric)):
            raise ValueError("Scaling thresholds must be strictly increasing")
        sizes = [level.mnq for level in self.levels]
        if sizes != sorted(sizes):
            raise ValueError("Scaling MNQ counts must be nondecreasing")
        if self.maximum_mnq != max(sizes):
            raise ValueError("maximum_mnq must equal the largest scheduled size")
        if self.scope == "per_account" and self.synchronized_aggregation is not None:
            raise ValueError("Per-account scaling cannot define book aggregation")
        if self.scope == "synchronized_book" and self.synchronized_aggregation is None:
            raise ValueError("Synchronized scaling requires an aggregation rule")

    def _scheduled_mnq(self, metric_usd: float) -> int:
        if not math.isfinite(metric_usd):
            raise ValueError("Scaling metric must be finite")
        selected = self.levels[0].mnq
        for level in self.levels[1:]:
            assert level.minimum_metric_usd is not None
            crosses = (
                metric_usd >= level.minimum_metric_usd
                if self.threshold_operator == "greater_than_or_equal"
                else metric_usd > level.minimum_metric_usd
            )
            if not crosses:
                break
            selected = level.mnq
        return selected

    def contracts_for_metric(
        self, metric_usd: float, *, prior_mnq: int | None = None
    ) -> int:
        selected = self._scheduled_mnq(metric_usd)
        if self.downscale_rule == "sticky_max":
            if (
                not isinstance(prior_mnq, int)
                or isinstance(prior_mnq, bool)
                or prior_mnq <= 0
            ):
                raise ValueError("sticky_max scaling requires a positive integer prior_mnq")
            selected = max(selected, prior_mnq)
        return min(selected, self.maximum_mnq)

    def contracts_for_accounts(
        self,
        metrics_by_pa_id: Mapping[int, float],
        *,
        prior_mnq_by_pa_id: Mapping[int, int] | None = None,
    ) -> dict[int, int]:
        ordered = dict(sorted(metrics_by_pa_id.items()))
        if any(
            not isinstance(pa_id, int) or isinstance(pa_id, bool) or pa_id <= 0
            for pa_id in ordered
        ):
            raise ValueError("Scaling account identifiers must be positive integers")
        if not ordered:
            return {}
        prior = prior_mnq_by_pa_id or {}
        if self.scope == "per_account":
            return {
                pa_id: self.contracts_for_metric(
                    metric, prior_mnq=prior.get(pa_id)
                )
                for pa_id, metric in ordered.items()
            }
        if self.synchronized_aggregation != "minimum_eligible_metric":
            raise ValueError("Unsupported synchronized aggregation")
        common_metric = min(ordered.values())
        raw = self._scheduled_mnq(common_metric)
        if self.downscale_rule == "sticky_max":
            if set(prior) != set(ordered) or any(value <= 0 for value in prior.values()):
                raise ValueError(
                    "Synchronized sticky_max requires every eligible prior MNQ count"
                )
            raw = max(raw, max(prior.values()))
        common = min(raw, self.maximum_mnq)
        return {pa_id: common for pa_id in ordered}


@dataclass(frozen=True, slots=True)
class BookPipelineState:
    """One explicitly named pipeline-cap accounting state; never PA inventory."""

    target_active_pas: int
    active_pa_ids: tuple[int, ...]
    target_accounting: PipelineTargetAccounting
    running_evaluation_ids: tuple[str, ...] = ()
    pending_activation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.target_active_pas, int)
            or isinstance(self.target_active_pas, bool)
            or not 1 <= self.target_active_pas <= 20
        ):
            raise ValueError("Active-PA target must be an integer in 1..20")
        if self.target_accounting != "active_plus_running_and_pending":
            raise ValueError("Unsupported pipeline target-accounting rule")
        if any(
            not isinstance(pa_id, int) or isinstance(pa_id, bool) or pa_id <= 0
            for pa_id in self.active_pa_ids
        ):
            raise ValueError("Active PA identifiers must be positive integers")
        for name, values in (
            ("active PA", self.active_pa_ids),
            ("running Evaluation", self.running_evaluation_ids),
            ("pending activation", self.pending_activation_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {name} identifier")
            if any(value == "" for value in values):
                raise ValueError(f"Empty {name} identifier")
        if self.capacity_commitments > self.target_active_pas:
            raise ValueError("Capacity commitments overshoot the active-PA hard cap")

    @property
    def capacity_commitments(self) -> int:
        return (
            len(self.active_pa_ids)
            + len(self.running_evaluation_ids)
            + len(self.pending_activation_ids)
        )

    @property
    def open_slots(self) -> int:
        return self.target_active_pas - self.capacity_commitments


@dataclass(frozen=True, slots=True)
class AcquisitionPolicy:
    policy_id: str
    mode: Literal["none", "one_per_decision", "fill_open_slots", "fixed_cadence"]
    max_purchases_per_decision: int
    max_running_evaluations: int | None
    cadence_days: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in {
            "none",
            "one_per_decision",
            "fill_open_slots",
            "fixed_cadence",
        }:
            raise ValueError("Unsupported acquisition mode")
        if (
            not self.policy_id
            or not isinstance(self.max_purchases_per_decision, int)
            or isinstance(self.max_purchases_per_decision, bool)
            or self.max_purchases_per_decision <= 0
        ):
            raise ValueError("Acquisition identity and positive integer event cap are required")
        if self.max_running_evaluations is not None and (
            not isinstance(self.max_running_evaluations, int)
            or isinstance(self.max_running_evaluations, bool)
            or self.max_running_evaluations <= 0
        ):
            raise ValueError("max_running_evaluations must be a positive integer")
        if self.mode == "fixed_cadence":
            if (
                not isinstance(self.cadence_days, int)
                or isinstance(self.cadence_days, bool)
                or self.cadence_days <= 0
            ):
                raise ValueError("fixed_cadence acquisition requires cadence_days")
        elif self.cadence_days is not None:
            raise ValueError("cadence_days is only valid for fixed_cadence")


@dataclass(frozen=True, slots=True)
class ReplacementPolicy:
    policy_id: str
    mode: Literal["never", "evaluation_pipeline"]
    max_purchases_per_death_event: int
    shares_acquisition_pipeline: bool = True

    def __post_init__(self) -> None:
        if self.mode not in {"never", "evaluation_pipeline"}:
            raise ValueError("Unsupported replacement mode")
        if (
            not self.policy_id
            or not isinstance(self.max_purchases_per_death_event, int)
            or isinstance(self.max_purchases_per_death_event, bool)
            or self.max_purchases_per_death_event <= 0
        ):
            raise ValueError("Replacement identity and positive integer death-event cap are required")
        if not isinstance(self.shares_acquisition_pipeline, bool):
            raise ValueError("Replacement pipeline-sharing flag must be boolean")
        if self.mode == "evaluation_pipeline" and not self.shares_acquisition_pipeline:
            raise ValueError("Replacement must use the observable Evaluation pipeline")


@dataclass(frozen=True, slots=True)
class EvaluationPurchaseIntent:
    reason: PurchaseReason
    slot_ordinal: int

    def __post_init__(self) -> None:
        if self.reason not in {"growth", "death_replacement"}:
            raise ValueError("Unsupported Evaluation purchase reason")
        if (
            not isinstance(self.slot_ordinal, int)
            or isinstance(self.slot_ordinal, bool)
            or self.slot_ordinal <= 0
        ):
            raise ValueError("Evaluation purchase ordinal must be a positive integer")

    @property
    def creates_pa_immediately(self) -> bool:
        return False


def plan_evaluation_purchase_intents(
    state: BookPipelineState,
    acquisition: AcquisitionPolicy,
    replacement: ReplacementPolicy,
    *,
    reason: PurchaseReason,
    cadence_due: bool = True,
    death_count: int | None = None,
) -> tuple[EvaluationPurchaseIntent, ...]:
    """Plan only Evaluation purchases; never manufacture an immediate PA."""

    if not isinstance(cadence_due, bool):
        raise ValueError("cadence_due must be boolean")
    if reason not in {"growth", "death_replacement"}:
        raise ValueError(f"Unsupported purchase reason: {reason}")
    if reason == "growth" and death_count is not None:
        raise ValueError("Growth acquisition cannot declare a death count")
    if reason == "death_replacement" and (
        not isinstance(death_count, int)
        or isinstance(death_count, bool)
        or death_count <= 0
    ):
        raise ValueError("Death replacement requires a positive integer death_count")
    if state.open_slots <= 0:
        return ()
    evaluation_room = (
        state.open_slots
        if acquisition.max_running_evaluations is None
        else max(
            0,
            acquisition.max_running_evaluations
            - len(state.running_evaluation_ids),
        )
    )
    limit = min(
        state.open_slots,
        evaluation_room,
        acquisition.max_purchases_per_decision,
    )
    if reason == "growth":
        if acquisition.mode == "none":
            return ()
        if acquisition.mode == "fixed_cadence" and not cadence_due:
            return ()
        if acquisition.mode in {"one_per_decision", "fixed_cadence"}:
            limit = min(limit, 1)
    else:
        if replacement.mode == "never":
            return ()
        assert death_count is not None
        limit = min(
            limit,
            replacement.max_purchases_per_death_event,
            death_count,
        )

    return tuple(
        EvaluationPurchaseIntent(reason=reason, slot_ordinal=index)
        for index in range(1, limit + 1)
    )
