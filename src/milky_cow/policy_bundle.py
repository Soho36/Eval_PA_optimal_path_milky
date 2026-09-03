"""Construct every runtime policy object from one typed configuration file.

This is the single seam between the configuration and executable code.
``config/runtime.json`` is the only source: no dataclass default may silently
supply a term that moves cash or changes an outcome. Rationale lives in
ASSUMPTIONS.md and current state in STATUS.md, neither of which is loaded here.

While the config lists blockers before a citable sweep, a caller must pass
``exploratory=True``; the resulting bundle carries that flag so every run
manifest can label itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .contracts import (
    AcquisitionPolicy,
    ReplacementPolicy,
    ScalingLevel,
    ScalingSchedule,
)
from .copy_to_all import CommissionTiming
from .evaluation import EvaluationRules
from .execution import ExecutionModel
from .inputs import PathStressArm
from .lifecycle import EventOrderMode, event_order_phase_ranks
from .payouts import Legacy25KPayoutRules, PayoutPolicy, load_payout_policies
from .treasury import ExternalCapitalPolicy

DEFAULT_CONFIG = "config/runtime.json"


@dataclass(frozen=True, slots=True)
class StudyPolicyBundle:
    """One fully resolved (N, payout policy, path arm, event order) arm."""

    config_path: str
    config_sha256: str
    target_active_pas: int
    payout_policy: PayoutPolicy
    scaling: ScalingSchedule
    acquisition: AcquisitionPolicy
    replacement: ReplacementPolicy
    capital: ExternalCapitalPolicy
    evaluation_rules: EvaluationRules
    payout_rules: Legacy25KPayoutRules
    path_stress_arm: PathStressArm
    commission_timing: CommissionTiming
    event_order_mode: EventOrderMode
    evaluation_fee_usd: float
    evaluation_renewal_fee_usd: float
    activation_fee_usd: float
    commission_usd_per_mnq: float
    starting_cash_usd: float
    horizon_days: int
    expected_pa_stream_sha256: str
    expected_pa_raw_offer_count: int
    execution: ExecutionModel
    exploratory: bool
    outstanding_blockers: tuple[str, ...]

    @property
    def arm_id(self) -> str:
        return (
            f"n{self.target_active_pas:02d}"
            f".{self.payout_policy.policy_id}"
            f".{self.path_stress_arm}"
            f".{self.event_order_mode}"
            f".{self.execution.model_id}"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blockers(config: dict[str, Any], *, allow: bool) -> tuple[str, ...]:
    """The config gates the run, or the run declares itself exploratory."""

    outstanding = tuple(config["status"].get("blockers_before_a_citable_sweep") or ())
    if outstanding and not allow:
        raise ValueError(
            "Config lists unfinished work before a citable sweep; pass "
            "exploratory=True to run anyway and have the result labelled "
            f"exploratory: {list(outstanding)}"
        )
    return outstanding


def _scaling(block: dict[str, Any]) -> ScalingSchedule:
    return ScalingSchedule(
        policy_id=block["selected_policy_id"],
        scope=block["scope"],
        threshold_metric=block["threshold_metric"],
        levels=tuple(
            ScalingLevel(
                minimum_metric_usd=level["minimum_metric_usd"],
                mnq=level["mnq"],
            )
            for level in block["levels"]
        ),
        threshold_operator=block["threshold_operator"],
        decision_time=block["decision_time"],
        downscale_rule=block["downscale_rule"],
        synchronized_aggregation=block["synchronized_aggregation"],
        maximum_mnq=block["maximum_mnq"],
        outcome_scaling=block["outcome_scaling"],
    )


def _execution(config: dict[str, Any], override: str | None) -> ExecutionModel:
    """Build the execution model from config, not from a hard-coded constant."""

    block = config["execution"]
    model_id = override or block["selected_model_id"]
    catalog = block["models"]
    if model_id not in catalog:
        raise ValueError(f"Unsupported execution model: {model_id}")
    row = catalog[model_id]
    return ExecutionModel(
        model_id=model_id,
        slippage_ticks_per_side=row["slippage_ticks_per_side"],
        tick_value_usd=row["tick_value_usd"],
    )


def _capital(block: dict[str, Any]) -> ExternalCapitalPolicy:
    return ExternalCapitalPolicy(
        policy_id=block["selected_policy_id"],
        mode=block["mode"],
        permitted_uses=tuple(block["permitted_uses"]),
        lifetime_cap_usd=block["lifetime_hard_cap_usd"],
        contribution_timing=block["contribution_timing"],
        close_event=block["bridge_close_event"],
        reopens=block["bridge_reopens"],
        bridge_evaluation_id=block.get("bridge_chain_identity"),
    )


def load_policy_bundle(
    root: str | Path,
    *,
    target_active_pas: int,
    payout_policy_id: str,
    path_stress_arm: PathStressArm | None = None,
    event_order_mode: EventOrderMode | None = None,
    config_relative_path: str = DEFAULT_CONFIG,
    execution_model_id: str | None = None,
    exploratory: bool = False,
) -> StudyPolicyBundle:
    """Build one executable arm from the gate, or refuse and say why."""

    root = Path(root)
    config_path = root / config_relative_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    outstanding = _blockers(config, allow=exploratory)

    if target_active_pas not in config["pa_book"]["active_pa_count_values"]:
        raise ValueError(
            f"N={target_active_pas} is outside the declared count axis"
        )

    policies = {
        policy.policy_id: policy
        for policy in load_payout_policies(root / "config/payout_policies.json")
    }
    if payout_policy_id not in policies:
        raise ValueError(f"Unknown payout policy: {payout_policy_id}")
    if payout_policy_id not in set(config["payout"]["policy_ids"]):
        raise ValueError(f"Payout policy is not a declared candidate: {payout_policy_id}")

    path_block = config["intratrade_path_order"]
    arm = path_stress_arm or path_block["central_arm"]
    if arm not in path_block["scenario_arms"]:
        raise ValueError(f"Path arm is not a declared scenario arm: {arm}")

    order_mode = event_order_mode or config["event_order"]["selected"]
    event_order_phase_ranks(order_mode)

    terms = config["commercial_terms"]
    account_terms = config["evaluation"]
    stream = config["input_stream"]
    capital_block = config["external_capital"]

    return StudyPolicyBundle(
        config_path=config_relative_path,
        config_sha256=_sha256(config_path),
        target_active_pas=target_active_pas,
        payout_policy=policies[payout_policy_id],
        scaling=_scaling(config["scaling"]),
        acquisition=AcquisitionPolicy(
            policy_id=config["acquisition"]["selected_policy_id"],
            mode=config["acquisition"]["mode"],
            max_purchases_per_decision=config["acquisition"]["max_purchases_per_decision"],
            max_running_evaluations=config["acquisition"]["maximum_running_evaluations"],
            cadence_days=config["acquisition"]["cadence_days"],
        ),
        replacement=ReplacementPolicy(
            policy_id=config["replacement"]["selected_policy_id"],
            mode=config["replacement"]["mode"],
            max_purchases_per_death_event=config["replacement"][
                "max_purchases_per_death_event"
            ],
            shares_acquisition_pipeline=config["replacement"]["shares_evaluation_pipeline"],
        ),
        capital=_capital(capital_block),
        evaluation_rules=EvaluationRules(
            target_profit_usd=account_terms["target_profit_usd"],
            trailing_drawdown_usd=account_terms["trailing_drawdown_usd"],
            contracts_mnq=account_terms["contracts_mnq"],
            minimum_trading_days=account_terms["minimum_trading_days"],
            cycle_days=account_terms["cycle_days"],
            threshold_touch_fails=account_terms["threshold_touch_fails"],
            carries_if_alive_at_renewal=account_terms["carries_if_alive_at_renewal"],
        ),
        payout_rules=Legacy25KPayoutRules(**config["payout"]["rules"]),
        path_stress_arm=arm,
        commission_timing=config["scaling"]["commission_timing"],
        event_order_mode=order_mode,
        evaluation_fee_usd=terms["evaluation_purchase_fee_usd"],
        evaluation_renewal_fee_usd=terms["evaluation_renewal_fee_usd"],
        activation_fee_usd=terms["pa_activation_fee_usd"],
        commission_usd_per_mnq=terms["commission_roundturn_usd_per_mnq"],
        starting_cash_usd=capital_block["starting_cash_usd"],
        horizon_days=config["reporting"]["horizon_days"],
        expected_pa_stream_sha256=stream["accepted_stream_sha256"],
        expected_pa_raw_offer_count=stream["expected_raw_offers"],
        execution=_execution(config, execution_model_id),
        exploratory=exploratory,
        outstanding_blockers=outstanding,
    )
