"""Thin deterministic coordinator for executable lifecycle contract fixtures.

This module composes the independently tested Evaluation, copy-to-all, payout,
pipeline, and treasury primitives. It is intentionally not a sweep framework
and does not choose the unresolved real-study policies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
import math
from typing import Literal

from .contracts import (
    AcquisitionPolicy,
    BookPipelineState,
    EvaluationPurchaseIntent,
    ReplacementPolicy,
    ScalingSchedule,
    plan_evaluation_purchase_intents,
)
from .copy_to_all import (
    CommissionTiming,
    CopyDecision,
    PAAccount,
    PATradeResult,
    copy_to_all,
    settle_copy_decision,
)
from .evaluation import (
    EvaluationAccount,
    EvaluationRules,
    EvaluationTradeResult,
    begin_evaluation_trade,
    renew_evaluation,
    settle_evaluation_trade,
)
from .inputs import (
    AcceptedOpportunity,
    OpportunitySelection,
    PathStressArm,
    TradeOffer,
    money,
    path_order_for_offer,
)
from .payouts import (
    Legacy25KPayoutRules,
    PayoutPolicy,
    PayoutRecord,
    execute_atomic_payout_if_eligible,
)
from .treasury import ExternalCapitalPolicy, Treasury


LifecyclePhase = Literal[
    "pa_exit",
    "evaluation_exit",
    "zero_duration_evaluation_entry",
    "zero_duration_pa_entry",
    "zero_duration_pa_exit",
    "zero_duration_evaluation_exit",
    "payout",
    "renewal",
    "activation",
    "purchase",
    "evaluation_entry",
    "pa_entry",
]
_PHASE_RANK: dict[LifecyclePhase, int] = {
    "pa_exit": 10,
    "evaluation_exit": 20,
    "zero_duration_evaluation_entry": 22,
    "zero_duration_pa_entry": 24,
    "zero_duration_pa_exit": 26,
    "zero_duration_evaluation_exit": 28,
    "payout": 30,
    "renewal": 40,
    "activation": 50,
    "purchase": 60,
    "evaluation_entry": 70,
    "pa_entry": 80,
}


@dataclass(frozen=True, slots=True)
class LifecycleAuditEvent:
    event_at: datetime
    phase: LifecyclePhase
    event_type: str
    reference: str


@dataclass(frozen=True, slots=True)
class PendingActivation:
    evaluation_id: str
    passed_at: datetime


@dataclass(slots=True)
class Lifecycle:
    """Small explicit state machine used by deterministic contract traces."""

    target_active_pas: int
    treasury: Treasury
    capital_policy: ExternalCapitalPolicy
    scaling: ScalingSchedule
    acquisition_policy: AcquisitionPolicy
    replacement_policy: ReplacementPolicy
    payout_policy: PayoutPolicy
    path_stress_arm: PathStressArm
    commission_timing: CommissionTiming
    pa_opportunity_selection: OpportunitySelection
    expected_pa_stream_sha256: str
    expected_pa_raw_offer_count: int
    first_pa_opportunity_ordinal: int = 1
    evaluation_rules: EvaluationRules = field(default_factory=EvaluationRules)
    payout_rules: Legacy25KPayoutRules = field(default_factory=Legacy25KPayoutRules)
    evaluation_fee_usd: float = 35.0
    activation_fee_usd: float = 125.0
    aggregate_execution_assumption: Literal[
        "perfect_linear_no_slippage_fixture_only"
    ] = "perfect_linear_no_slippage_fixture_only"
    evaluations: dict[str, EvaluationAccount] = field(init=False, default_factory=dict)
    pending_activations: dict[str, PendingActivation] = field(
        init=False, default_factory=dict
    )
    pas: dict[int, PAAccount] = field(init=False, default_factory=dict)
    outstanding_pa_decisions: dict[str, CopyDecision] = field(
        init=False, default_factory=dict
    )
    copy_decisions: list[CopyDecision] = field(init=False, default_factory=list)
    pa_trade_results: list[PATradeResult] = field(init=False, default_factory=list)
    evaluation_trade_results: list[EvaluationTradeResult] = field(
        init=False, default_factory=list
    )
    payouts: list[PayoutRecord] = field(init=False, default_factory=list)
    audit: list[LifecycleAuditEvent] = field(init=False, default_factory=list)
    replacement_intent_count: int = field(init=False, default=0)
    unprocessed_pa_death_count: int = field(init=False, default=0)
    death_replacement_planning_due: bool = field(init=False, default=False)
    _next_evaluation_number: int = field(init=False, default=1)
    _next_pa_id: int = field(init=False, default=1)
    _next_pa_opportunity_ordinal: int = field(init=False)
    _purchase_decision_timestamps: set[datetime] = field(
        init=False, default_factory=set
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.target_active_pas, int)
            or isinstance(self.target_active_pas, bool)
            or not 1 <= self.target_active_pas <= 20
        ):
            raise ValueError("Lifecycle target must be an integer in 1..20")
        if self.path_stress_arm not in {
            "source_constrained_then_mae_first",
            "source_constrained_then_mfe_first",
            "source_constrained_then_seeded_coin",
        }:
            raise ValueError("Unsupported lifecycle path policy")
        if self.commission_timing not in {"close_only", "intratrade_and_close"}:
            raise ValueError("Unsupported lifecycle commission timing")
        if any(
            not math.isfinite(value) or value <= 0
            for value in (self.evaluation_fee_usd, self.activation_fee_usd)
        ):
            raise ValueError("Lifecycle fees must be finite and positive")
        if self.aggregate_execution_assumption != (
            "perfect_linear_no_slippage_fixture_only"
        ):
            raise ValueError("The contract fixture requires an explicit execution assumption")
        if not isinstance(self.pa_opportunity_selection, OpportunitySelection):
            raise ValueError("Lifecycle requires one explicit PA opportunity selection")
        if (
            self.pa_opportunity_selection.accepted_stream_sha256
            != self.expected_pa_stream_sha256
            or self.pa_opportunity_selection.raw_count
            != self.expected_pa_raw_offer_count
        ):
            raise ValueError("PA opportunity selection does not match its evidence binding")
        if (
            not isinstance(self.first_pa_opportunity_ordinal, int)
            or isinstance(self.first_pa_opportunity_ordinal, bool)
            or not 1
            <= self.first_pa_opportunity_ordinal
            <= len(self.pa_opportunity_selection.accepted)
        ):
            raise ValueError("First PA opportunity ordinal is outside the selected stream")
        self._next_pa_opportunity_ordinal = self.first_pa_opportunity_ordinal

    @property
    def active_pa_ids(self) -> tuple[int, ...]:
        return tuple(sorted(pa_id for pa_id, pa in self.pas.items() if pa.alive))

    @property
    def pipeline_state(self) -> BookPipelineState:
        return BookPipelineState(
            target_active_pas=self.target_active_pas,
            active_pa_ids=self.active_pa_ids,
            target_accounting="active_plus_running_and_pending",
            running_evaluation_ids=tuple(sorted(self.evaluations)),
            pending_activation_ids=tuple(sorted(self.pending_activations)),
        )

    @property
    def global_opportunity_count(self) -> int:
        return len(self.copy_decisions)

    @property
    def account_copy_count(self) -> int:
        return sum(decision.account_copy_count for decision in self.copy_decisions)

    @property
    def applied_copy_net_pnl_usd(self) -> float:
        return money(
            sum(
                result.net_pnl_usd or 0.0
                for result in self.pa_trade_results
                if result.completed_trade_outcome_applied
            )
        )

    def _record(
        self,
        event_at: datetime,
        phase: LifecyclePhase,
        event_type: str,
        reference: str,
    ) -> None:
        self._validate_event_order(event_at, phase)
        if not event_type or not reference:
            raise ValueError("Lifecycle events require type and reference")
        self.audit.append(LifecycleAuditEvent(event_at, phase, event_type, reference))

    def _validate_event_order(
        self,
        event_at: datetime,
        phase: LifecyclePhase,
    ) -> None:
        if event_at.tzinfo is None:
            raise ValueError("Lifecycle events must be timezone-aware")
        requested_rank = _PHASE_RANK[phase]
        due_exits: list[tuple[datetime, int]] = []
        for decision in self.outstanding_pa_decisions.values():
            due_phase: LifecyclePhase = (
                "zero_duration_pa_exit"
                if decision.entry_at == decision.exit_at
                else "pa_exit"
            )
            due_exits.append((decision.exit_at, _PHASE_RANK[due_phase]))
        for account in self.evaluations.values():
            if account.outstanding_trade is None:
                continue
            offer = account.outstanding_trade.offer
            due_phase = (
                "zero_duration_evaluation_exit"
                if offer.entry_at == offer.exit_at
                else "evaluation_exit"
            )
            due_exits.append((offer.exit_at, _PHASE_RANK[due_phase]))
        if any(
            event_at > due_at
            or (event_at == due_at and requested_rank > due_rank)
            for due_at, due_rank in due_exits
        ):
            raise ValueError("A due trade exit must settle before this lifecycle event")
        if self.audit:
            prior = self.audit[-1]
            if event_at < prior.event_at:
                raise ValueError("Lifecycle events must be chronological")
            if event_at == prior.event_at and requested_rank < _PHASE_RANK[prior.phase]:
                raise ValueError("Same-timestamp lifecycle phase order regressed")

    def _validate_treasury_event_order(self, event_at: datetime) -> None:
        if event_at.tzinfo is None:
            raise ValueError("Cash events must be timezone-aware")
        if self.treasury.ledger and event_at < self.treasury.ledger[-1].event_at:
            raise ValueError("Cash events must be chronological")
        activated_at = self.treasury.first_pa_activated_at
        if activated_at is not None and event_at < activated_at:
            raise ValueError("Cash event precedes the recorded first PA activation")

    def _purchase_intents(
        self,
        event_at: datetime,
        intents: tuple[EvaluationPurchaseIntent, ...],
    ) -> tuple[str, ...]:
        purchased: list[str] = []
        for intent in intents:
            evaluation_id = f"eval-{self._next_evaluation_number}"
            self._validate_event_order(event_at, "purchase")
            self._validate_treasury_event_order(event_at)
            paid = self.treasury.fund_and_pay_fee(
                event_at,
                self.evaluation_fee_usd,
                "evaluation_purchase",
                evaluation_id,
                self.capital_policy,
            )
            self._record(
                event_at,
                "purchase",
                "evaluation_purchased" if paid else "evaluation_purchase_unfunded",
                evaluation_id,
            )
            if not paid:
                break
            self.evaluations[evaluation_id] = EvaluationAccount(
                evaluation_id=evaluation_id,
                purchased_at=event_at,
                cycle_started_at=event_at,
                floor_profit_usd=money(-self.evaluation_rules.trailing_drawdown_usd),
            )
            self._next_evaluation_number += 1
            purchased.append(evaluation_id)
            self.pipeline_state
        return tuple(purchased)

    def _claim_purchase_decision(self, event_at: datetime) -> None:
        if event_at in self._purchase_decision_timestamps:
            raise ValueError(
                "Only one Evaluation purchase decision is allowed per timestamp"
            )
        self._validate_event_order(event_at, "purchase")
        self._purchase_decision_timestamps.add(event_at)

    def plan_growth_and_purchase(self, event_at: datetime) -> tuple[str, ...]:
        if self.unprocessed_pa_death_count:
            raise ValueError("Death replacements must be processed before growth")
        intents = plan_evaluation_purchase_intents(
            self.pipeline_state,
            self.acquisition_policy,
            self.replacement_policy,
            reason="growth",
        )
        self._claim_purchase_decision(event_at)
        return self._purchase_intents(event_at, intents)

    def plan_death_replacements_and_purchase(
        self,
        event_at: datetime,
        death_count: int,
    ) -> tuple[str, ...]:
        if death_count != self.unprocessed_pa_death_count:
            raise ValueError(
                "Death replacement count must match the unprocessed PA deaths"
            )
        intents = plan_evaluation_purchase_intents(
            self.pipeline_state,
            self.acquisition_policy,
            self.replacement_policy,
            reason="death_replacement",
            death_count=death_count,
        )
        self._claim_purchase_decision(event_at)
        purchased = self._purchase_intents(event_at, intents)
        if self.replacement_policy.mode == "never":
            self.unprocessed_pa_death_count = 0
        else:
            self.replacement_intent_count += len(purchased)
            self.unprocessed_pa_death_count -= len(purchased)
        self.death_replacement_planning_due = False
        return purchased

    def begin_evaluation_offer(self, evaluation_id: str, offer: TradeOffer) -> None:
        if self.death_replacement_planning_due:
            raise ValueError("Death replacements must be processed before new entries")
        account = self.evaluations.get(evaluation_id)
        if account is None:
            raise ValueError(f"Unknown running Evaluation: {evaluation_id}")
        phase: LifecyclePhase = (
            "zero_duration_evaluation_entry"
            if offer.entry_at == offer.exit_at
            else "evaluation_entry"
        )
        self._validate_event_order(offer.entry_at, phase)
        begin_evaluation_trade(account, offer, self.evaluation_rules)
        self._record(offer.entry_at, phase, "evaluation_trade_entered", offer.trade_key)

    def begin_pa_opportunity(self, opportunity: AcceptedOpportunity) -> CopyDecision:
        key = opportunity.offer.trade_key
        if key in self.outstanding_pa_decisions:
            raise ValueError("PA opportunity is already outstanding")
        if self.outstanding_pa_decisions:
            raise ValueError("The prior PA copy batch must settle before the next entry")
        if self.death_replacement_planning_due:
            raise ValueError("Death replacements must be processed before new entries")
        ordinal = self._next_pa_opportunity_ordinal
        if ordinal > len(self.pa_opportunity_selection.accepted):
            raise ValueError("PA opportunity stream is already exhausted")
        expected = self.pa_opportunity_selection.accepted_opportunities[ordinal - 1]
        if opportunity != expected:
            raise ValueError(
                "PA opportunity is not the next member of the bound global stream"
            )
        phase: LifecyclePhase = (
            "zero_duration_pa_entry"
            if opportunity.offer.entry_at == opportunity.offer.exit_at
            else "pa_entry"
        )
        self._validate_event_order(opportunity.offer.entry_at, phase)
        decision = copy_to_all(
            opportunity,
            list(self.pas.values()),
            self.scaling,
        )
        self.outstanding_pa_decisions[key] = decision
        self.copy_decisions.append(decision)
        self._record(opportunity.offer.entry_at, phase, "pa_copy_batch_created", key)
        self._next_pa_opportunity_ordinal += 1
        return decision

    def settle_pa_opportunity(self, trade_key: str, event_at: datetime) -> tuple[PATradeResult, ...]:
        decision = self.outstanding_pa_decisions.get(trade_key)
        if decision is None:
            raise ValueError(f"Unknown outstanding PA opportunity: {trade_key}")
        phase: LifecyclePhase = (
            "zero_duration_pa_exit"
            if decision.entry_at == decision.exit_at
            else "pa_exit"
        )
        self._validate_event_order(event_at, phase)
        results = settle_copy_decision(
            decision,
            self.pas,
            event_at=event_at,
            path_order=path_order_for_offer(
                decision.opportunity.offer,
                self.path_stress_arm,
            ),
            commission_timing=self.commission_timing,
        )
        del self.outstanding_pa_decisions[trade_key]
        self._record(event_at, phase, "pa_copy_batch_settled", trade_key)
        self.pa_trade_results.extend(results)
        deaths = sum(not result.survived for result in results)
        self.unprocessed_pa_death_count += deaths
        if deaths:
            self.death_replacement_planning_due = True
        self.pipeline_state
        return results

    def settle_evaluation_offer(
        self,
        evaluation_id: str,
        event_at: datetime,
    ) -> EvaluationTradeResult:
        account = self.evaluations.get(evaluation_id)
        if account is None or account.outstanding_trade is None:
            raise ValueError(f"Unknown or idle Evaluation: {evaluation_id}")
        offer = account.outstanding_trade.offer
        phase: LifecyclePhase = (
            "zero_duration_evaluation_exit"
            if offer.entry_at == offer.exit_at
            else "evaluation_exit"
        )
        self._validate_event_order(event_at, phase)
        result = settle_evaluation_trade(
            account,
            event_at=event_at,
            path_order=path_order_for_offer(offer, self.path_stress_arm),
            rules=self.evaluation_rules,
        )
        self._record(event_at, phase, "evaluation_trade_settled", offer.trade_key)
        self.evaluation_trade_results.append(result)
        if result.status == "passed":
            del self.evaluations[evaluation_id]
            self.pending_activations[evaluation_id] = PendingActivation(
                evaluation_id,
                event_at,
            )
        self.pipeline_state
        return result

    def fund_pending_activation(
        self,
        evaluation_id: str,
        event_at: datetime,
    ) -> PAAccount | None:
        pending = self.pending_activations.get(evaluation_id)
        if pending is None:
            raise ValueError(f"Unknown pending activation: {evaluation_id}")
        if event_at < pending.passed_at:
            raise ValueError("Activation funding cannot precede the Evaluation pass")
        self._validate_event_order(event_at, "activation")
        self._validate_treasury_event_order(event_at)
        paid = self.treasury.fund_and_pay_fee(
            event_at,
            self.activation_fee_usd,
            "pa_activation",
            evaluation_id,
            self.capital_policy,
        )
        self._record(
            event_at,
            "activation",
            "pa_activated" if paid else "pa_activation_unfunded",
            evaluation_id,
        )
        if not paid:
            return None
        pa = PAAccount(
            pa_id=self._next_pa_id,
            activated_at=event_at,
            liquidation_floor_profit_usd=-1_500.0,
        )
        self.pas[pa.pa_id] = pa
        self._next_pa_id += 1
        del self.pending_activations[evaluation_id]
        if self.treasury.first_pa_activated_at is None:
            self.treasury.observe_first_pa_activation(event_at)
        self.pipeline_state
        return pa

    def execute_session_close_payouts(self, event_at: datetime) -> tuple[PayoutRecord, ...]:
        executed: list[PayoutRecord] = []
        self._validate_event_order(event_at, "payout")
        self._validate_treasury_event_order(event_at)
        if event_at.timetz().replace(tzinfo=None) != time(23, 59):
            raise ValueError(
                "Session-close payouts must execute at exactly 23:59:00"
            )
        if self.outstanding_pa_decisions:
            raise ValueError(
                "Payout with an outstanding PA copy is outside the locked fixture contract"
            )
        for pa_id in self.active_pa_ids:
            account = self.pas[pa_id]
            account_snapshot = (
                account.equity_profit_usd,
                account.payout_count,
                account.cumulative_gross_payouts_usd,
                account.cumulative_net_payouts_usd,
                dict(account.payout_period_daily_pnl_usd),
            )
            treasury_snapshot = (
                self.treasury.cash_usd,
                self.treasury.payout_receipts_usd,
                len(self.treasury.ledger),
            )
            audit_length = len(self.audit)
            payout_length = len(self.payouts)
            try:
                record = execute_atomic_payout_if_eligible(
                    account,
                    event_at,
                    self.payout_policy,
                    self.payout_rules,
                )
                if record is None:
                    continue
                self.treasury.receive_payout(
                    event_at,
                    record.treasury_receipt_usd,
                    f"pa-{pa_id}:payout-{record.payout_number}",
                )
                self._record(event_at, "payout", "payout_executed", f"pa-{pa_id}")
                self.payouts.append(record)
                executed.append(record)
            except Exception:
                (
                    account.equity_profit_usd,
                    account.payout_count,
                    account.cumulative_gross_payouts_usd,
                    account.cumulative_net_payouts_usd,
                    period_history,
                ) = account_snapshot
                account.payout_period_daily_pnl_usd = period_history
                (
                    self.treasury.cash_usd,
                    self.treasury.payout_receipts_usd,
                    ledger_length,
                ) = treasury_snapshot
                del self.treasury.ledger[ledger_length:]
                del self.audit[audit_length:]
                del self.payouts[payout_length:]
                raise
        return tuple(executed)

    def fund_and_renew_evaluation(self, evaluation_id: str, event_at: datetime) -> bool:
        account = self.evaluations.get(evaluation_id)
        if account is None:
            raise ValueError(f"Unknown running Evaluation: {evaluation_id}")
        self._validate_event_order(event_at, "renewal")
        self._validate_treasury_event_order(event_at)
        if event_at.tzinfo is None or event_at != account.cycle_due_at(
            self.evaluation_rules
        ):
            raise ValueError("Evaluation renewal must occur at the exact cycle boundary")
        if account.status == "passed" or account.outstanding_trade is not None:
            raise ValueError("Passed or busy Evaluations cannot renew")
        paid = self.treasury.fund_and_pay_fee(
            event_at,
            self.evaluation_fee_usd,
            "evaluation_renewal",
            evaluation_id,
            self.capital_policy,
        )
        self._record(
            event_at,
            "renewal",
            "evaluation_renewed" if paid else "evaluation_renewal_unfunded",
            evaluation_id,
        )
        if paid:
            renew_evaluation(account, event_at, self.evaluation_rules)
        else:
            del self.evaluations[evaluation_id]
        self.pipeline_state
        return paid

    def assert_integrity(self) -> None:
        self.treasury.assert_integrity()
        self.pipeline_state
        if len(self.pas) != len(set(self.pas)) or len(self.evaluations) != len(
            set(self.evaluations)
        ):
            raise RuntimeError("Lifecycle identifiers are not unique")
        if set(self.pending_activations) & set(self.evaluations):
            raise RuntimeError("Evaluation cannot be running and pending activation")
        if self.unprocessed_pa_death_count < 0:
            raise RuntimeError("Unprocessed PA death count cannot be negative")
        if self.death_replacement_planning_due and not self.unprocessed_pa_death_count:
            raise RuntimeError("Death-planning flag has no matching death obligation")
        if self._next_pa_opportunity_ordinal != (
            self.first_pa_opportunity_ordinal + len(self.copy_decisions)
        ):
            raise RuntimeError("PA opportunity consumption index is inconsistent")
        unsettled = {
            decision.opportunity_key
            for decision in self.copy_decisions
            if decision.settled_at is None
        }
        if unsettled != set(self.outstanding_pa_decisions):
            raise RuntimeError("Outstanding PA decision index is inconsistent")
        for pa_id, account in self.pas.items():
            applied = money(
                sum(
                    result.net_pnl_usd or 0.0
                    for result in self.pa_trade_results
                    if result.pa_id == pa_id and result.completed_trade_outcome_applied
                )
            )
            expected_equity = money(applied - account.cumulative_gross_payouts_usd)
            if expected_equity != account.equity_profit_usd:
                raise RuntimeError(
                    f"PA {pa_id} equity reconciliation mismatch: "
                    f"{expected_equity} != {account.equity_profit_usd}"
                )
        prior: LifecycleAuditEvent | None = None
        for event in self.audit:
            if prior is not None:
                if event.event_at < prior.event_at or (
                    event.event_at == prior.event_at
                    and _PHASE_RANK[event.phase] < _PHASE_RANK[prior.phase]
                ):
                    raise RuntimeError("Lifecycle audit order is inconsistent")
            prior = event
