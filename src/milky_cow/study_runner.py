"""Drive one cohort of the copy-to-all lifecycle over the real RR1 tape.

The runner owns only sequencing. Every policy comes from the gate through
``StudyPolicyBundle``, every state transition goes through ``Lifecycle``, and
the declared same-timestamp phase order is honored by processing phases in
rank order at each event timestamp.

Scope: this is a single-cohort driver that produces one result manifest. It is
not the parameter sweep.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from .cohorts import CohortWindow
from .copy_to_all import PAAccount
from .evaluation_consumer import CycleLocalEvaluationConsumer
from .inputs import OpportunitySelection, TradeOffer, VerifiedRR1Dataset, money
from .lifecycle import Lifecycle, event_order_phase_ranks
from .policy_bundle import StudyPolicyBundle
from .treasury import Treasury

SESSION_CLOSE = time(23, 59)


@dataclass(slots=True)
class CohortResult:
    """One executed cohort, ready to serialize as a result manifest."""

    arm_id: str
    config_sha256: str
    start_at: datetime
    horizon_end_at: datetime
    target_active_pas: int
    payout_policy_id: str
    path_stress_arm: str
    event_order_mode: str
    execution_model_id: str

    owner_capital_supplied_usd: float
    owner_net_retained_cash_usd: float
    cumulative_payout_harvest_usd: float
    ending_cash_usd: float
    fees_paid_usd: float

    evaluations_purchased: int
    evaluation_renewals_paid: int
    evaluation_renewals_unfunded: int
    evaluations_passed: int
    pas_activated: int
    pa_deaths: int
    first_pa_activated_at: datetime | None

    surviving_pa_count: int
    surviving_unwithdrawn_equity_usd: float
    payouts_executed: int
    payouts_deferred_open_copy: int

    pa_opportunities_consumed: int
    account_copies_applied: int
    evaluation_trades: int
    evaluation_offers_blocked_busy: int
    evaluation_boundary_closed_cycles: int

    horizon_open_batches: int
    horizon_open_copy_count: int

    correlated_death_events: int
    max_simultaneous_deaths: int

    cash_bound_days: float
    pipeline_bound_days: float
    dormant_slot_days: float
    book_full_days: float
    growth_ready_days: float

    audit_events: int

    def as_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "milky_cow_cohort_result.v1",
            "arm": {
                "arm_id": self.arm_id,
                "target_active_pas": self.target_active_pas,
                "payout_policy_id": self.payout_policy_id,
                "path_stress_arm": self.path_stress_arm,
                "event_order_mode": self.event_order_mode,
                "execution_model_id": self.execution_model_id,
            },
            "provenance": {
                "config_sha256": self.config_sha256,
                "status": "single_cohort_slice_not_a_study_result",
            },
            "cohort": {
                "start_at": self.start_at.isoformat(),
                "horizon_end_at": self.horizon_end_at.isoformat(),
            },
            "headline": {
                "owner_net_retained_cash_usd": self.owner_net_retained_cash_usd,
                "cumulative_payout_harvest_usd": self.cumulative_payout_harvest_usd,
                "owner_capital_supplied_usd": self.owner_capital_supplied_usd,
                "ending_cash_usd": self.ending_cash_usd,
                "fees_paid_usd": self.fees_paid_usd,
            },
            "right_censoring_companion": {
                "surviving_pa_count": self.surviving_pa_count,
                "surviving_unwithdrawn_equity_usd": self.surviving_unwithdrawn_equity_usd,
                "horizon_open_batches": self.horizon_open_batches,
                "horizon_open_copy_count": self.horizon_open_copy_count,
                "note": "unwithdrawn equity is never summed into the headline",
            },
            "pipeline": {
                "evaluations_purchased": self.evaluations_purchased,
                "evaluation_renewals_paid": self.evaluation_renewals_paid,
                "evaluation_renewals_unfunded": self.evaluation_renewals_unfunded,
                "evaluations_passed": self.evaluations_passed,
                "pas_activated": self.pas_activated,
                "pa_deaths": self.pa_deaths,
                "first_pa_activated_at": (
                    self.first_pa_activated_at.isoformat()
                    if self.first_pa_activated_at
                    else None
                ),
            },
            "streams": {
                "pa_opportunities_consumed": self.pa_opportunities_consumed,
                "account_copies_applied": self.account_copies_applied,
                "evaluation_trades": self.evaluation_trades,
                "evaluation_offers_blocked_busy": self.evaluation_offers_blocked_busy,
                "evaluation_boundary_closed_cycles": self.evaluation_boundary_closed_cycles,
            },
            "payouts": {
                "executed": self.payouts_executed,
                "deferred_open_copy": self.payouts_deferred_open_copy,
            },
            "correlated_failure": {
                "death_events_killing_more_than_one_pa": self.correlated_death_events,
                "max_simultaneous_deaths": self.max_simultaneous_deaths,
                "note": (
                    "the copy-to-all signature: one trade can retire several "
                    "PAs at once, which staggering at R=1 cannot do"
                ),
            },
            "constraint_time_days": {
                "cash_bound": self.cash_bound_days,
                "pipeline_bound": self.pipeline_bound_days,
                "book_full": self.book_full_days,
                "growth_ready": self.growth_ready_days,
                "dormant_slot_days": self.dormant_slot_days,
                "note": (
                    "cash_bound + pipeline_bound + book_full + growth_ready "
                    "equals the cohort length exactly; dormant_slot_days is a "
                    "separate measure summed per blocked slot"
                ),
            },
            "audit_events": self.audit_events,
        }


def _first_ordinal_at_or_after(
    selection: OpportunitySelection, moment: datetime
) -> int | None:
    for ordinal, offer in enumerate(selection.accepted, start=1):
        if offer.entry_at >= moment:
            return ordinal
    return None


def _next_session_close(after: datetime) -> datetime:
    """The first 23:59 local close strictly after ``after``."""

    candidate = after.replace(
        hour=SESSION_CLOSE.hour, minute=SESSION_CLOSE.minute, second=0, microsecond=0
    )
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


@dataclass(slots=True)
class _Runner:
    bundle: StudyPolicyBundle
    dataset: VerifiedRR1Dataset
    cohort: CohortWindow
    lifecycle: Lifecycle
    consumer: CycleLocalEvaluationConsumer
    renewals_paid: int = 0
    renewals_unfunded: int = 0
    passes: int = 0
    activations: int = 0
    deaths: int = 0
    payouts_executed: int = 0
    opportunities_consumed: int = 0
    cash_bound_seconds: float = 0.0
    pipeline_bound_seconds: float = 0.0
    dormant_slot_seconds: float = 0.0
    book_full_seconds: float = 0.0
    growth_ready_seconds: float = 0.0
    _last_close: datetime | None = field(default=None)
    _prev_now: datetime | None = field(default=None)

    # -- next-event computation ------------------------------------------
    def _next_pa_entry(self) -> datetime | None:
        life = self.lifecycle
        ordinal = life._next_pa_opportunity_ordinal
        accepted = life.pa_opportunity_selection.accepted
        if ordinal > len(accepted):
            return None
        entry_at = accepted[ordinal - 1].entry_at
        return entry_at if entry_at < self.cohort.horizon_end_at else None

    def _next_event_at(self) -> datetime | None:
        life = self.lifecycle
        candidates: list[datetime] = []
        for decision in life.outstanding_pa_decisions.values():
            candidates.append(decision.exit_at)
        for account in life.evaluations.values():
            if account.outstanding_trade is not None:
                candidates.append(account.outstanding_trade.offer.exit_at)
                continue
            candidates.append(account.cycle_due_at(self.bundle.evaluation_rules))
            offer = self.consumer.next_offer(account, self.bundle.evaluation_rules)
            if offer is not None:
                candidates.append(offer.entry_at)
        pa_entry = self._next_pa_entry()
        if pa_entry is not None:
            candidates.append(pa_entry)
        if life.pending_activations and any(
            self._can_fund(
                self.bundle.activation_fee_usd, "pa_activation", evaluation_id
            )
            for evaluation_id in life.pending_activations
        ):
            # An unfundable activation must not drive the clock: it stays
            # pending, holding its pipeline slot, until some other event brings
            # in cash. _activations retries it at every timestamp anyway.
            candidates.extend(
                pending.passed_at for pending in life.pending_activations.values()
            )
        live = [moment for moment in candidates if moment >= self._floor()]
        pending_close = self._pending_close()
        if pending_close is not None:
            live.append(pending_close)
        if not live:
            return None
        return min(live)

    def _pending_close(self) -> datetime | None:
        """The next 23:59 close a payout could execute at.

        Anchored on the last close actually reached, not on the audit log: a
        close where every PA defers or nothing is eligible records nothing, and
        anchoring on the audit would stop proposing closes entirely.
        """

        if not self.lifecycle.pas:
            return None
        anchor = self._last_close if self._last_close is not None else self._floor()
        return _next_session_close(anchor)

    def _accrue_constraint_time(self, now: datetime) -> None:
        """Attribute elapsed time to the reason the book was not at target.

        This is what turns "pipeline time rather than cash binds at large N"
        from an inference off the activation plateau into a measurement.
        """

        previous = self._prev_now
        self._prev_now = now
        if previous is None or now <= previous:
            return
        seconds = (now - previous).total_seconds()
        life = self.lifecycle
        dormant = sum(
            1 for account in life.evaluations.values() if account.status == "failed"
        )
        self.dormant_slot_seconds += dormant * seconds
        active = len(life.active_pa_ids)
        if active >= self.bundle.target_active_pas:
            self.book_full_seconds += seconds
            return
        committed = active + len(life.evaluations) + len(life.pending_activations)
        if committed >= self.bundle.target_active_pas:
            # Every slot is held by a running or dormant Evaluation or a
            # pending activation: the book is waiting on the pipeline.
            self.pipeline_bound_seconds += seconds
        elif not self._can_fund(
            self.bundle.evaluation_fee_usd,
            "evaluation_purchase",
            f"eval-{life._next_evaluation_number}",
        ):
            self.cash_bound_seconds += seconds
        else:
            # Below target, a slot free and the fee affordable: the book is
            # simply between the opportunity and the purchase. Attributing it
            # keeps the four buckets summing to the exact cohort length.
            self.growth_ready_seconds += seconds

    def _settles_at_horizon(self, now: datetime) -> bool:
        """An exit landing exactly on the horizon settles; nothing else runs.

        The contract forbids settling an exit *strictly* after the cutoff, so
        the boundary instant itself is inside the cohort. Stopping at `>=`
        would strand one real RR1 opportunity as a phantom open batch.
        """

        life = self.lifecycle
        if any(
            decision.exit_at == now
            for decision in life.outstanding_pa_decisions.values()
        ):
            return True
        return any(
            account.outstanding_trade is not None
            and account.outstanding_trade.offer.exit_at == now
            for account in life.evaluations.values()
        )

    def _floor(self) -> datetime:
        life = self.lifecycle
        return life.audit[-1].event_at if life.audit else self.cohort.start_at

    # -- phase handlers ---------------------------------------------------
    def _settle_pa_exits(self, now: datetime) -> None:
        life = self.lifecycle
        for key, decision in list(life.outstanding_pa_decisions.items()):
            if decision.exit_at == now:
                before = {pa_id for pa_id in life.active_pa_ids}
                life.settle_pa_opportunity(key, now)
                self.deaths += len(before - set(life.active_pa_ids))

    def _settle_evaluation_exits(self, now: datetime) -> None:
        life = self.lifecycle
        for evaluation_id, account in list(life.evaluations.items()):
            trade = account.outstanding_trade
            if trade is not None and trade.offer.exit_at == now:
                result = life.settle_evaluation_offer(evaluation_id, now)
                if result.status == "passed":
                    self.passes += 1

    def _payouts(self, now: datetime) -> None:
        if now >= self.cohort.horizon_end_at:
            return
        if now.timetz().replace(tzinfo=None) != SESSION_CLOSE:
            return
        # Record the close as reached before deciding anything, so a close at
        # which nothing happens still advances the schedule.
        self._last_close = now
        if not self.lifecycle.pas:
            return
        executed = self.lifecycle.execute_session_close_payouts(now)
        self.payouts_executed += len(executed)

    def _renewals(self, now: datetime) -> None:
        if now >= self.cohort.horizon_end_at:
            return
        life = self.lifecycle
        for evaluation_id, account in list(life.evaluations.items()):
            if account.outstanding_trade is not None:
                continue
            if account.cycle_due_at(self.bundle.evaluation_rules) != now:
                continue
            if now >= self.cohort.horizon_end_at:
                continue
            if life.fund_and_renew_evaluation(evaluation_id, now):
                self.renewals_paid += 1
            else:
                self.renewals_unfunded += 1

    def _activations(self, now: datetime) -> None:
        if now >= self.cohort.horizon_end_at:
            return
        life = self.lifecycle
        for evaluation_id, pending in list(life.pending_activations.items()):
            if pending.passed_at > now:
                continue
            # An unfunded attempt leaves the activation pending, so retrying it
            # at every timestamp would stall the clock. Wait for cash instead.
            if not self._can_fund(
                self.bundle.activation_fee_usd, "pa_activation", evaluation_id
            ):
                continue
            if life.fund_pending_activation(evaluation_id, now) is not None:
                self.activations += 1

    def _can_fund(
        self, amount_usd: float, purpose: str, reference: str | None = None
    ) -> bool:
        """Mirror Treasury.fund_and_pay_fee's affordability test exactly.

        Without this precondition an unfundable obligation is retried at every
        event timestamp. That changes no cash, but a pending activation is
        never cleared by a failed attempt, so the clock stops advancing and the
        audit grows without bound.
        """

        treasury = self.lifecycle.treasury
        shortfall = money(max(0.0, amount_usd - treasury.cash_usd))
        if not shortfall:
            return True
        return self.bundle.capital.authorizes(
            purpose,
            bridge_closed=treasury.external_bridge_closed_for(self.bundle.capital),
            contributed_usd=treasury.external_contributions_usd,
            shortfall_usd=shortfall,
            reference=reference,
            activated_evaluation_ids=treasury.pa_activations_by_evaluation.keys(),
        )

    def _purchases(self, now: datetime) -> None:
        life = self.lifecycle
        if now >= self.cohort.horizon_end_at:
            return
        if now in life._purchase_decision_timestamps:
            return
        # A fresh death must be decided even when nothing can be funded: the
        # planning flag blocks new PA entries until the decision is recorded,
        # and "no purchase" is a decision.
        must_decide_death = life.death_replacement_planning_due
        next_id = f"eval-{life._next_evaluation_number}"
        affordable = self._can_fund(
            self.bundle.evaluation_fee_usd, "evaluation_purchase", next_id
        )
        if life.unprocessed_pa_death_count and (must_decide_death or affordable):
            life.plan_death_replacements_and_purchase(
                now, life.unprocessed_pa_death_count
            )
            return
        if not affordable:
            return
        state = life.pipeline_state
        committed = (
            len(state.active_pa_ids)
            + len(state.running_evaluation_ids)
            + len(state.pending_activation_ids)
        )
        if committed < self.bundle.target_active_pas:
            life.plan_growth_and_purchase(now)

    def _evaluation_entries(self, now: datetime) -> None:
        if now >= self.cohort.horizon_end_at:
            return
        life = self.lifecycle
        for evaluation_id, account in list(life.evaluations.items()):
            offer = self.consumer.next_offer(account, self.bundle.evaluation_rules)
            if offer is None or offer.entry_at != now:
                continue
            if offer.entry_at >= self.cohort.horizon_end_at:
                continue
            self.consumer.consume(account, offer)
            life.begin_evaluation_offer(evaluation_id, offer)

    def _pa_entry(self, now: datetime) -> None:
        entry_at = self._next_pa_entry()
        if entry_at != now:
            return
        life = self.lifecycle
        ordinal = life._next_pa_opportunity_ordinal
        opportunity = life.pa_opportunity_selection.accepted_opportunities[ordinal - 1]
        life.begin_pa_opportunity(opportunity)
        self.opportunities_consumed += 1

    def run(self) -> None:
        # Seed the clock at the cohort start so the interval before the first
        # event is classified rather than silently dropped.
        self._prev_now = self.cohort.start_at
        # Cohort start: the owner seed buys the bridge Evaluation.
        self._purchases(self.cohort.start_at)
        handlers = {
            "pa_exit": self._settle_pa_exits,
            "evaluation_exit": self._settle_evaluation_exits,
            "payout": self._payouts,
            "renewal": self._renewals,
            "activation": self._activations,
            "purchase": self._purchases,
            "evaluation_entry": self._evaluation_entries,
            "pa_entry": self._pa_entry,
        }
        ranks = event_order_phase_ranks(self.bundle.event_order_mode)
        # Zero-duration phases share their handler with the positive-duration
        # phase of the same kind; the lifecycle picks the right phase label.
        ordered_phases = [
            phase
            for phase, _ in sorted(ranks.items(), key=lambda item: item[1])
            if phase in handlers
        ]
        guard = 0
        while True:
            guard += 1
            if guard > 2_000_000:
                raise RuntimeError("Cohort event loop failed to terminate")
            now = self._next_event_at()
            if now is None or now > self.cohort.horizon_end_at:
                break
            if now == self.cohort.horizon_end_at and not self._settles_at_horizon(now):
                break
            self._accrue_constraint_time(now)
            for phase in ordered_phases:
                handlers[phase](now)
        # The interval from the last event to the horizon is still cohort time
        # and must be attributed, as is the head interval before the first
        # event (handled by seeding _prev_now at the cohort start).
        self._accrue_constraint_time(self.cohort.horizon_end_at)


def run_cohort(
    bundle: StudyPolicyBundle,
    dataset: VerifiedRR1Dataset,
    cohort: CohortWindow,
) -> CohortResult:
    """Execute one cohort and return its result manifest data."""

    selection = dataset.selection
    first_ordinal = _first_ordinal_at_or_after(selection, cohort.start_at)
    if first_ordinal is None:
        raise ValueError("Cohort start is past the end of the accepted stream")

    lifecycle = Lifecycle(
        target_active_pas=bundle.target_active_pas,
        treasury=Treasury(starting_cash_usd=bundle.starting_cash_usd),
        capital_policy=bundle.capital,
        scaling=bundle.scaling,
        acquisition_policy=bundle.acquisition,
        replacement_policy=bundle.replacement,
        payout_policy=bundle.payout_policy,
        path_stress_arm=bundle.path_stress_arm,
        commission_timing=bundle.commission_timing,
        pa_opportunity_selection=selection,
        expected_pa_stream_sha256=bundle.expected_pa_stream_sha256,
        expected_pa_raw_offer_count=bundle.expected_pa_raw_offer_count,
        first_pa_opportunity_ordinal=first_ordinal,
        event_order_mode=bundle.event_order_mode,
        evaluation_rules=bundle.evaluation_rules,
        payout_rules=bundle.payout_rules,
        execution=bundle.execution,
        evaluation_fee_usd=bundle.evaluation_fee_usd,
        evaluation_renewal_fee_usd=bundle.evaluation_renewal_fee_usd,
        activation_fee_usd=bundle.activation_fee_usd,
    )
    runner = _Runner(
        bundle=bundle,
        dataset=dataset,
        cohort=cohort,
        lifecycle=lifecycle,
        consumer=CycleLocalEvaluationConsumer(dataset.offers),
    )
    runner.run()
    lifecycle.assert_integrity()

    treasury = lifecycle.treasury
    survivors = [lifecycle.pas[pa_id] for pa_id in lifecycle.active_pa_ids]
    totals = runner.consumer.totals()
    deferred = sum(
        1
        for event in lifecycle.audit
        if event.event_type == "payout_deferred_open_copy"
    )
    open_copies = sum(
        len(decision.copies) for decision in lifecycle.outstanding_pa_decisions.values()
    )
    deaths_by_trade = Counter(
        result.trade_key for result in lifecycle.pa_trade_results if not result.survived
    )
    simultaneous = [count for count in deaths_by_trade.values() if count > 1]
    return CohortResult(
        arm_id=bundle.arm_id,
        config_sha256=bundle.config_sha256,
        start_at=cohort.start_at,
        horizon_end_at=cohort.horizon_end_at,
        target_active_pas=bundle.target_active_pas,
        payout_policy_id=bundle.payout_policy.policy_id,
        path_stress_arm=bundle.path_stress_arm,
        event_order_mode=bundle.event_order_mode,
        execution_model_id=bundle.execution.model_id,
        owner_capital_supplied_usd=treasury.owner_capital_supplied_usd,
        owner_net_retained_cash_usd=treasury.owner_net_retained_cash_usd,
        cumulative_payout_harvest_usd=treasury.payout_receipts_usd,
        ending_cash_usd=treasury.cash_usd,
        fees_paid_usd=treasury.fees_paid_usd,
        evaluations_purchased=lifecycle._next_evaluation_number - 1,
        evaluation_renewals_paid=runner.renewals_paid,
        evaluation_renewals_unfunded=runner.renewals_unfunded,
        evaluations_passed=runner.passes,
        pas_activated=runner.activations,
        pa_deaths=runner.deaths,
        first_pa_activated_at=treasury.first_pa_activated_at,
        surviving_pa_count=len(survivors),
        surviving_unwithdrawn_equity_usd=money(
            sum(account.equity_profit_usd for account in survivors)
        ),
        payouts_executed=runner.payouts_executed,
        payouts_deferred_open_copy=deferred,
        pa_opportunities_consumed=runner.opportunities_consumed,
        account_copies_applied=lifecycle.account_copy_count,
        evaluation_trades=totals.admitted,
        evaluation_offers_blocked_busy=totals.blocked_busy,
        evaluation_boundary_closed_cycles=totals.boundary_closed_cycles,
        horizon_open_batches=len(lifecycle.outstanding_pa_decisions),
        horizon_open_copy_count=open_copies,
        correlated_death_events=len(simultaneous),
        max_simultaneous_deaths=max(simultaneous, default=0),
        cash_bound_days=round(runner.cash_bound_seconds / 86_400.0, 3),
        pipeline_bound_days=round(runner.pipeline_bound_seconds / 86_400.0, 3),
        dormant_slot_days=round(runner.dormant_slot_seconds / 86_400.0, 3),
        book_full_days=round(runner.book_full_seconds / 86_400.0, 3),
        growth_ready_days=round(runner.growth_ready_seconds / 86_400.0, 3),
        audit_events=len(lifecycle.audit),
    )
