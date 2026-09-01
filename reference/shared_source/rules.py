"""Validated Legacy 25K study rules and policy configuration."""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class Legacy25KRules:
    nominal_balance_usd: float = 25_000.0
    evaluation_profit_target_usd: float = 1_500.0
    evaluation_trailing_drawdown_usd: float = 1_500.0
    evaluation_fee_usd: float = 35.0
    activation_fee_usd: float = 125.0
    evaluation_contracts_mnq: int = 3
    evaluation_minimum_trading_days: int = 1
    evaluation_cycle_days: int = 30
    evaluation_threshold_touch_fails: bool = True
    evaluation_carries_if_alive_at_renewal: bool = True
    activation_delay_seconds: int = 0
    pa_trailing_drawdown_usd: float = 1_500.0
    pa_frozen_floor_profit_usd: float = 100.0
    pa_threshold_touch_fails: bool = True
    payout_minimum_days: int = 8
    payout_minimum_profitable_days: int = 5
    payout_profitable_day_usd: float = 50.0
    payout_request_gate_balance_usd: float = 26_600.0
    payout_safety_net_balance_usd: float = 26_600.0
    payout_minimum_request_usd: float = 500.0
    payout_first_five_cap_usd: float = 1_500.0
    payout_safety_net_request_count: int = 3
    payout_cap_request_count: int = 5
    payout_post_safety_minimum_balance_usd: float = 25_100.01
    payout_full_split_cumulative_usd: float = 25_000.0
    payout_split_after_full: float = 0.90
    commission_roundturn_usd_per_mnq: float = 1.05

    def __post_init__(self) -> None:
        positive = (
            "nominal_balance_usd",
            "evaluation_profit_target_usd",
            "evaluation_trailing_drawdown_usd",
            "evaluation_fee_usd",
            "activation_fee_usd",
            "evaluation_contracts_mnq",
            "evaluation_minimum_trading_days",
            "evaluation_cycle_days",
            "pa_trailing_drawdown_usd",
            "payout_minimum_days",
            "payout_minimum_profitable_days",
            "payout_minimum_request_usd",
        )
        for name in positive:
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.activation_delay_seconds < 0:
            raise ValueError("activation_delay_seconds cannot be negative")
        if self.payout_minimum_profitable_days > self.payout_minimum_days:
            raise ValueError(
                "payout_minimum_profitable_days cannot exceed payout_minimum_days"
            )
        if self.payout_minimum_request_usd > self.payout_first_five_cap_usd:
            raise ValueError("payout minimum cannot exceed the first-five cap")
        if self.payout_safety_net_request_count > self.payout_cap_request_count:
            raise ValueError("safety-net payout count cannot exceed capped payout count")
        if self.payout_post_safety_minimum_balance_usd <= (
            self.nominal_balance_usd + self.pa_frozen_floor_profit_usd
        ):
            raise ValueError(
                "post-safety payout balance must remain above the frozen PA floor"
            )
        if not 0 < self.payout_split_after_full <= 1:
            raise ValueError("payout_split_after_full must be in (0, 1]")


PayoutRuleKind = Literal["minimum", "maximum", "fixed", "fraction"]

# The 2026-08-30 comparison set. It varies the axis the Legacy 25K rules
# actually bind on: how the five capped payouts are spent before the cap and
# the Safety Net both disappear, and how much cushion is left in the account.
BASELINE_POLICY_IDS = {
    "minimum_500_always",
    "maximum_always",
    "rush_to_uncapped",
    "cap_maximizer",
    "preserve_safety_net",
    "half_of_maximum",
}


@dataclass(frozen=True, slots=True)
class PayoutRule:
    """How one request amount is chosen once eligibility already holds."""

    kind: PayoutRuleKind
    amount_usd: float | None = None
    fraction: float | None = None
    require_full: bool = True

    def __post_init__(self) -> None:
        if self.kind == "fixed":
            if not self.amount_usd or self.amount_usd <= 0:
                raise ValueError("fixed payout rule requires a positive amount_usd")
            if self.fraction is not None:
                raise ValueError("fixed payout rule does not accept a fraction")
        elif self.kind == "fraction":
            if self.fraction is None or not 0 < self.fraction <= 1:
                raise ValueError("fraction payout rule requires fraction in (0, 1]")
            if self.amount_usd is not None:
                raise ValueError("fraction payout rule does not accept amount_usd")
        elif self.kind in {"minimum", "maximum"}:
            if self.amount_usd is not None or self.fraction is not None:
                raise ValueError(f"{self.kind} payout rule takes no amount or fraction")
        else:
            raise ValueError(f"Unsupported payout rule kind: {self.kind}")


@dataclass(frozen=True, slots=True)
class PayoutPolicy:
    """A per-PA withdrawal policy.

    ``early_rule`` applies until ``switch_after_payout_number`` executed payouts
    exist on that PA, after which ``late_rule`` applies. This exists because the
    firm rules change shape at payout 4 (Safety Net ends) and payout 6 (the
    fixed cap ends), so "how fast do I burn the five capped payouts" is a real
    decision rather than a calibration detail.
    """

    policy_id: str
    early_rule: PayoutRule
    switch_after_payout_number: int | None = None
    late_rule: PayoutRule | None = None
    post_payout_floor_balance_usd: float | None = None
    accumulated_profit_trigger_usd: float | None = None

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("policy_id is required")
        if (self.late_rule is None) != (self.switch_after_payout_number is None):
            raise ValueError(
                "late_rule and switch_after_payout_number must be set together"
            )
        if (
            self.switch_after_payout_number is not None
            and self.switch_after_payout_number <= 0
        ):
            raise ValueError("switch_after_payout_number must be positive")
        if (
            self.post_payout_floor_balance_usd is not None
            and self.post_payout_floor_balance_usd <= 0
        ):
            raise ValueError("post_payout_floor_balance_usd must be positive")
        if (
            self.accumulated_profit_trigger_usd is not None
            and self.accumulated_profit_trigger_usd <= 0
        ):
            raise ValueError("accumulated_profit_trigger_usd must be positive")

    def rule_for(self, executed_payouts: int) -> PayoutRule:
        if (
            self.late_rule is not None
            and self.switch_after_payout_number is not None
            and executed_payouts >= self.switch_after_payout_number
        ):
            return self.late_rule
        return self.early_rule

    @classmethod
    def of(cls, policy_id: str, kind: PayoutRuleKind, **kwargs: Any) -> "PayoutPolicy":
        """Build a single-rule policy. Convenience for tests and fixtures."""

        rule_fields = {"amount_usd", "fraction", "require_full"}
        rule_kwargs = {k: v for k, v in kwargs.items() if k in rule_fields}
        policy_kwargs = {k: v for k, v in kwargs.items() if k not in rule_fields}
        return cls(policy_id, PayoutRule(kind, **rule_kwargs), **policy_kwargs)


# Treasury purchase timing. K is an outcome of these rules, not an input:
# a container must be earned through a $35 Evaluation with a median 61-day lag,
# so *when* to spend payout cash is the staggering decision in this project.
PURCHASE_POLICIES = (
    "greedy_to_target",
    "fixed_cadence",
    "death_replacement",
    "headroom_triggered",
    "cash_buffer",
)

BOOTSTRAP_FUNDING_MODES = (
    "through_first_pa",
    "through_inventory_target",
)


@dataclass(frozen=True, slots=True)
class StudyConfig:
    timezone: str = "Europe/Tallinn"
    session_open: str = "01:00"
    session_close: str = "23:59"
    pa_requested_copies_r: int = 1
    target_pa_count_k: int = 5
    standby_pa_target: int = 0
    routing_policy: str = "max_headroom"
    product_availability: str = "always_in_study"
    evaluation_intratrade_path: str = "resolved"
    pa_intratrade_path: str = "mae_first"
    max_evaluation_purchases_per_event: int = 1
    max_concurrent_evaluations: int | None = None
    bootstrap_external_funding_until_first_pa: bool = True
    bootstrap_funding_mode: Literal[
        "through_first_pa", "through_inventory_target"
    ] = "through_first_pa"
    purchase_policy: str = "greedy_to_target"
    purchase_cadence_days: int | None = None
    purchase_headroom_trigger_usd: float | None = None
    purchase_cash_reserve_usd: float | None = None

    def __post_init__(self) -> None:
        if self.pa_requested_copies_r <= 0:
            raise ValueError("pa_requested_copies_r must be positive")
        if self.target_pa_count_k <= 0:
            raise ValueError("target_pa_count_k must be positive")
        if self.standby_pa_target < 0:
            raise ValueError("standby_pa_target cannot be negative")
        if self.max_evaluation_purchases_per_event <= 0:
            raise ValueError("max_evaluation_purchases_per_event must be positive")
        if (
            self.max_concurrent_evaluations is not None
            and self.max_concurrent_evaluations <= 0
        ):
            raise ValueError("max_concurrent_evaluations must be positive")
        if self.bootstrap_funding_mode not in BOOTSTRAP_FUNDING_MODES:
            raise ValueError(
                f"Unsupported bootstrap_funding_mode: {self.bootstrap_funding_mode}; "
                f"expected one of {sorted(BOOTSTRAP_FUNDING_MODES)}"
            )
        if (
            self.bootstrap_funding_mode == "through_inventory_target"
            and not self.bootstrap_external_funding_until_first_pa
        ):
            raise ValueError(
                "through_inventory_target requires the external funding bridge"
            )
        if self.purchase_policy not in PURCHASE_POLICIES:
            raise ValueError(
                f"Unsupported purchase_policy: {self.purchase_policy}; "
                f"expected one of {sorted(PURCHASE_POLICIES)}"
            )
        if self.purchase_policy == "fixed_cadence" and not self.purchase_cadence_days:
            raise ValueError("fixed_cadence requires purchase_cadence_days")
        if self.purchase_cadence_days is not None and self.purchase_cadence_days <= 0:
            raise ValueError("purchase_cadence_days must be positive")
        if (
            self.purchase_policy == "headroom_triggered"
            and self.purchase_headroom_trigger_usd is None
        ):
            raise ValueError(
                "headroom_triggered requires purchase_headroom_trigger_usd"
            )
        if (
            self.purchase_headroom_trigger_usd is not None
            and self.purchase_headroom_trigger_usd <= 0
        ):
            raise ValueError("purchase_headroom_trigger_usd must be positive")
        if (
            self.purchase_policy == "cash_buffer"
            and self.purchase_cash_reserve_usd is None
        ):
            raise ValueError("cash_buffer requires purchase_cash_reserve_usd")
        if (
            self.purchase_cash_reserve_usd is not None
            and self.purchase_cash_reserve_usd < 0
        ):
            raise ValueError("purchase_cash_reserve_usd cannot be negative")
        if self.routing_policy != "max_headroom":
            raise ValueError("The initial integrated baseline supports max_headroom only")
        if self.product_availability != "always_in_study":
            raise ValueError("The initial study contract requires perpetual Legacy availability")
        if self.evaluation_intratrade_path not in {"resolved", "mae_first", "mfe_first"}:
            raise ValueError("Unsupported evaluation_intratrade_path")
        if self.pa_intratrade_path not in {"resolved", "mae_first", "mfe_first"}:
            raise ValueError("Unsupported pa_intratrade_path")


def _strict_dataclass(cls, values: dict[str, Any]):
    known = {field.name for field in fields(cls)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} fields: {sorted(unknown)}")
    return cls(**values)


def load_baseline_config(path: str | Path) -> tuple[Legacy25KRules, StudyConfig]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = payload.get("schema_version")
    if schema == 1:  # compact developer fixture format
        if payload.get("schema_id") not in {None, "legacy_25k_baseline.v1"}:
            raise ValueError("Unsupported baseline config schema_id")
        return (
            _strict_dataclass(Legacy25KRules, payload["rules"]),
            _strict_dataclass(StudyConfig, payload["study"]),
        )
    if schema != "legacy_25k_baseline.v1":
        raise ValueError("Unsupported baseline config schema_version")
    commercial = payload["commercial_terms"]
    evaluation = payload["evaluation"]
    pa = payload["pa"]
    payout = payload["payout_rules"]
    split = payout["trader_split"]
    strategy = payload["fixed_strategy"]
    purchase = payload.get("purchase_policy", {"policy": "greedy_to_target"})
    rules = Legacy25KRules(
        nominal_balance_usd=float(payload["scope"]["nominal_balance_usd"]),
        evaluation_profit_target_usd=float(evaluation["profit_target_usd"]),
        evaluation_trailing_drawdown_usd=float(
            evaluation["trailing_drawdown"]["amount_usd"]
        ),
        evaluation_fee_usd=float(commercial["evaluation_purchase_fee_usd"]),
        activation_fee_usd=float(commercial["pa_activation_fee_usd"]),
        evaluation_contracts_mnq=int(evaluation["position_size_mnq"]),
        evaluation_minimum_trading_days=int(evaluation["minimum_trading_days"]),
        evaluation_cycle_days=int(commercial["evaluation_cycle_calendar_days"]),
        evaluation_threshold_touch_fails=bool(
            evaluation["trailing_drawdown"]["threshold_touch_fails"]
        ),
        evaluation_carries_if_alive_at_renewal=(
            evaluation["renewal"]["alive_state_at_boundary"]
            == "renew_and_carry_balance_peak_and_threshold"
        ),
        activation_delay_seconds=int(payload["activation"]["delay_seconds"]),
        pa_trailing_drawdown_usd=float(pa["trailing_drawdown"]["amount_usd"]),
        pa_frozen_floor_profit_usd=float(
            pa["trailing_drawdown"]["maximum_threshold_usd"]
            - payload["scope"]["nominal_balance_usd"]
        ),
        pa_threshold_touch_fails=bool(
            pa["trailing_drawdown"]["threshold_touch_fails"]
        ),
        payout_minimum_days=int(
            payout["minimum_trading_days_since_activation_or_last_request"]
        ),
        payout_minimum_profitable_days=int(payout["minimum_profitable_days"]),
        payout_profitable_day_usd=float(payout["profitable_day_threshold_net_usd"]),
        payout_request_gate_balance_usd=float(payout["request_gate_balance_usd"]),
        payout_safety_net_balance_usd=float(payout["request_gate_balance_usd"]),
        payout_minimum_request_usd=float(payout["minimum_gross_request_usd"]),
        payout_first_five_cap_usd=float(
            payout["maximum_gross_request_first_five_usd"]
        ),
        payout_safety_net_request_count=3,
        payout_cap_request_count=5,
        payout_post_safety_minimum_balance_usd=25_100.01,
        payout_full_split_cumulative_usd=float(
            split["cumulative_gross_threshold_usd"]
        ),
        payout_split_after_full=float(split["share_after_threshold"]),
        commission_roundturn_usd_per_mnq=float(
            strategy["commission_round_turn_usd_per_mnq"]
        ),
    )
    study = StudyConfig(
        timezone=payload["time"]["source_timezone"],
        session_open=payload["time"]["session_open_local"],
        session_close=payload["time"]["session_close_local"],
        pa_requested_copies_r=int(pa["exposure"]["requested_copies_r"]),
        target_pa_count_k=int(pa["router"].get("target_pa_count_k", 5)),
        standby_pa_target=int(pa["router"].get("standby_pa_target", 0)),
        routing_policy=pa["router"]["candidate"],
        product_availability="always_in_study",
        evaluation_intratrade_path="resolved",
        pa_intratrade_path="mae_first",
        max_evaluation_purchases_per_event=1,
        max_concurrent_evaluations=payload.get("account_inventory", {}).get(
            "max_concurrent_evaluations"
        ),
        bootstrap_external_funding_until_first_pa=True,
        bootstrap_funding_mode=payload.get("account_inventory", {}).get(
            "bootstrap_funding_mode", "through_first_pa"
        ),
        purchase_policy=purchase["policy"],
        purchase_cadence_days=purchase.get("cadence_days"),
        purchase_headroom_trigger_usd=purchase.get("headroom_trigger_usd"),
        purchase_cash_reserve_usd=purchase.get("cash_reserve_usd"),
    )
    return rules, study


def _payout_rule(payload: dict[str, Any]) -> PayoutRule:
    known = {"kind", "amount_usd", "fraction", "require_full"}
    unknown = set(payload) - known
    if unknown:
        raise ValueError(f"Unknown payout rule fields: {sorted(unknown)}")
    return PayoutRule(
        kind=payload["kind"],
        amount_usd=payload.get("amount_usd"),
        fraction=payload.get("fraction"),
        require_full=bool(payload.get("require_full", True)),
    )


def _payout_policy(payload: dict[str, Any]) -> PayoutPolicy:
    known = {
        "policy_id",
        "label",
        "description",
        "early_rule",
        "switch_after_payout_number",
        "late_rule",
        "post_payout_floor_balance_usd",
        "accumulated_profit_trigger_usd",
    }
    unknown = set(payload) - known
    if unknown:
        raise ValueError(f"Unknown payout policy fields: {sorted(unknown)}")
    late = payload.get("late_rule")
    return PayoutPolicy(
        policy_id=payload["policy_id"],
        early_rule=_payout_rule(payload["early_rule"]),
        switch_after_payout_number=payload.get("switch_after_payout_number"),
        late_rule=_payout_rule(late) if late is not None else None,
        post_payout_floor_balance_usd=payload.get("post_payout_floor_balance_usd"),
        accumulated_profit_trigger_usd=payload.get("accumulated_profit_trigger_usd"),
    )


def load_payout_policies(
    path: str | Path, *, require_baseline_set: bool = True
) -> list[PayoutPolicy]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise ValueError(
            "Unsupported payout-policy schema_version; expected 2 "
            "(the 2026-08-30 comparison set)"
        )
    if payload.get("schema_id") not in {None, "legacy_25k_payout_policies.v2"}:
        raise ValueError("Unsupported payout-policy schema_id")
    policies = [_payout_policy(row) for row in payload["policies"]]
    ids = [policy.policy_id for policy in policies]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate payout policy_id")
    if require_baseline_set and set(ids) != BASELINE_POLICY_IDS:
        missing = sorted(BASELINE_POLICY_IDS - set(ids))
        extra = sorted(set(ids) - BASELINE_POLICY_IDS)
        raise ValueError(
            f"Baseline payout policy set mismatch; missing={missing}, extra={extra}"
        )
    return policies
