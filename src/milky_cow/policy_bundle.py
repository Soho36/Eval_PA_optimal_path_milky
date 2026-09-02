"""Construct every runtime policy object from the active contract gate.

This is the single seam between the resolved contract and executable code. The
gate is the only source: no dataclass default may silently supply a term that
moves cash or changes an outcome. A gate whose contract fields are unresolved,
or whose bound evidence no longer hashes, cannot produce a bundle.
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
from .inputs import PathStressArm
from .lifecycle import EventOrderMode, event_order_phase_ranks
from .payouts import Legacy25KPayoutRules, PayoutPolicy, load_payout_policies
from .treasury import ExternalCapitalPolicy

DEFAULT_GATE = "config/milky_cow_contract_gate.json"


@dataclass(frozen=True, slots=True)
class StudyPolicyBundle:
    """One fully resolved (N, payout policy, path arm, event order) arm."""

    gate_path: str
    gate_sha256: str
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

    @property
    def arm_id(self) -> str:
        return (
            f"n{self.target_active_pas:02d}"
            f".{self.payout_policy.policy_id}"
            f".{self.path_stress_arm}"
            f".{self.event_order_mode}"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_resolved(gate: dict[str, Any]) -> None:
    unresolved = gate.get("unresolved_before_integrated_sweep")
    if unresolved:
        raise ValueError(
            "Gate contract fields are unresolved; refusing to build a runtime "
            f"bundle: {sorted(unresolved)}"
        )
    open_questions = gate.get("open_questions_requiring_user_decision") or ()
    if open_questions:
        raise ValueError(
            "Gate carries open user decisions; refusing to build a runtime "
            f"bundle: {sorted(q['id'] for q in open_questions)}"
        )


def _verify_evidence(root: Path, gate: dict[str, Any]) -> None:
    stale = [
        row["path"]
        for row in gate["evidence_bindings"]
        if _sha256(root / row["path"]) != row["sha256"]
    ]
    if stale:
        raise ValueError(f"Gate evidence bindings are stale: {sorted(stale)}")


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
    gate_relative_path: str = DEFAULT_GATE,
) -> StudyPolicyBundle:
    """Build one executable arm from the gate, or refuse and say why."""

    root = Path(root)
    gate_path = root / gate_relative_path
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    _require_resolved(gate)
    _verify_evidence(root, gate)

    if target_active_pas not in gate["pa_book"]["active_pa_count_values"]:
        raise ValueError(
            f"N={target_active_pas} is outside the gate's declared count axis"
        )

    policies = {
        policy.policy_id: policy
        for policy in load_payout_policies(root / "config/payout_policies.json")
    }
    if payout_policy_id not in policies:
        raise ValueError(f"Unknown payout policy: {payout_policy_id}")
    if payout_policy_id not in set(gate["payout_candidates"]["policy_ids"]):
        raise ValueError(f"Payout policy is not a gate candidate: {payout_policy_id}")

    path_block = gate["intratrade_path_order"]
    arm = path_stress_arm or path_block["central_arm"]
    if arm not in path_block["scenario_arms"]:
        raise ValueError(f"Path arm is not a declared scenario arm: {arm}")

    order_mode = event_order_mode or gate["event_order"]["selected"]
    event_order_phase_ranks(order_mode)

    terms = gate["commercial_terms"]
    account_terms = gate["evaluation_rule_boundaries"]["evaluation_account_terms"]
    stream = gate["opportunity_stream"]
    capital_block = gate["external_capital"]

    return StudyPolicyBundle(
        gate_path=gate_relative_path,
        gate_sha256=_sha256(gate_path),
        target_active_pas=target_active_pas,
        payout_policy=policies[payout_policy_id],
        scaling=_scaling(gate["scaling"]),
        acquisition=AcquisitionPolicy(
            policy_id=gate["acquisition"]["selected_policy_id"],
            mode=gate["acquisition"]["mode"],
            max_purchases_per_decision=gate["acquisition"]["max_purchases_per_decision"],
            max_running_evaluations=gate["acquisition"]["maximum_running_evaluations"],
            cadence_days=gate["acquisition"]["cadence_days"],
        ),
        replacement=ReplacementPolicy(
            policy_id=gate["replacement"]["selected_policy_id"],
            mode=gate["replacement"]["mode"],
            max_purchases_per_death_event=gate["replacement"][
                "max_purchases_per_death_event"
            ],
            shares_acquisition_pipeline=gate["replacement"]["shares_evaluation_pipeline"],
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
        payout_rules=Legacy25KPayoutRules(),
        path_stress_arm=arm,
        commission_timing=gate["scaling"]["commission_timing"],
        event_order_mode=order_mode,
        evaluation_fee_usd=terms["evaluation_purchase_fee_usd"],
        evaluation_renewal_fee_usd=terms["evaluation_renewal_fee_usd"],
        activation_fee_usd=terms["pa_activation_fee_usd"],
        commission_usd_per_mnq=terms["commission_roundturn_usd_per_mnq"],
        starting_cash_usd=capital_block["starting_cash_usd"],
        horizon_days=gate["reporting"]["horizon_and_right_censoring"]["primary_days"],
        expected_pa_stream_sha256=stream["accepted_stream_key_sha256"],
        expected_pa_raw_offer_count=stream["expected_raw_offers"],
    )
