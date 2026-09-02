from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from milky_cow.contracts import (
    AcquisitionPolicy,
    ReplacementPolicy,
    ScalingLevel,
    ScalingSchedule,
)
from milky_cow.copy_to_all import PAAccount
from milky_cow.evaluation import (
    EvaluationAccount,
    EvaluationRules,
    begin_evaluation_trade,
    renew_evaluation,
    settle_evaluation_trade,
)
from milky_cow.inputs import (
    OpportunitySelection,
    TradeOffer,
    get_timezone,
    resolve_path_order,
    select_global_one_position,
)
from milky_cow.lifecycle import Lifecycle
from milky_cow.payouts import (
    choose_payout_amount,
    execute_atomic_payout_if_eligible,
    load_payout_policies,
    maximum_eligible_gross,
)
from milky_cow.treasury import ExternalCapitalPolicy, Treasury


ROOT = Path(__file__).resolve().parents[1]
ZONE = get_timezone("Europe/Tallinn")


def at(label: str) -> datetime:
    return datetime.strptime(label, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZONE)


def fixture_offer(
    key: str,
    source_row: int,
    entry: str,
    exit: str,
    *,
    mae: float,
    mfe: float,
    gross: float,
) -> TradeOffer:
    entry_naive = datetime.strptime(entry, "%Y-%m-%d %H:%M:%S")
    exit_naive = datetime.strptime(exit, "%Y-%m-%d %H:%M:%S")
    raw = (
        f"{source_row}\t{entry}\t{exit}\t{mae:.2f}\t{mfe:.2f}\t"
        f"{gross:.2f}\t1.00\n"
    ).encode("utf-8")
    return TradeOffer(
        trade_key=key,
        strategy_id="deterministic_lifecycle_fixture",
        window_id="10-11",
        window_order=10,
        source_row=source_row,
        ticket=source_row,
        source_entry_label=entry,
        source_exit_label=exit,
        source_timezone_rule="Europe/Tallinn:fixture",
        entry_at=at(entry),
        exit_at=at(exit),
        mae_usd_per_mnq=mae,
        mfe_usd_per_mnq=mfe,
        gross_pnl_usd_per_mnq=gross,
        candle_range=1.0,
        commission_usd_per_mnq=1.05,
        resolved_path_order=resolve_path_order(
            entry_naive,
            exit_naive,
            mae,
            mfe,
            gross,
        ),
        source_file_sha256=hashlib.sha256(raw).hexdigest(),
    )


def fixed_one_mnq() -> ScalingSchedule:
    return ScalingSchedule(
        policy_id="fixture_fixed_one_mnq",
        scope="per_account",
        threshold_metric="realized_balance_usd",
        levels=(ScalingLevel(None, 1),),
        threshold_operator="greater_than_or_equal",
        decision_time="entry_before_trade_after_prior_same_timestamp_events",
        downscale_rule="immediate",
        synchronized_aggregation=None,
        maximum_mnq=1,
        outcome_scaling="linear_per_mnq",
    )


def lifecycle(
    target: int,
    *,
    starting_cash: float,
    capital_mode: str,
    selection: OpportunitySelection,
) -> Lifecycle:
    policies = load_payout_policies(ROOT / "config" / "payout_policies.json")
    payout = next(
        policy for policy in policies if policy.policy_id == "minimum_500_always"
    )
    if capital_mode == "through_first_pa":
        capital = ExternalCapitalPolicy(
            policy_id="fixture_through_first_pa",
            mode="through_first_pa",
            permitted_uses=(
                "evaluation_purchase",
                "evaluation_renewal",
                "pa_activation",
            ),
            lifetime_cap_usd=None,
            contribution_timing="just_in_time_exact_shortfall",
            close_event="first_pa_activated",
            reopens=False,
        )
    else:
        capital = ExternalCapitalPolicy(
            policy_id="fixture_no_external_capital",
            mode="none",
            permitted_uses=(),
            lifetime_cap_usd=0.0,
            contribution_timing="just_in_time_exact_shortfall",
            close_event="never",
            reopens=False,
        )
    return Lifecycle(
        target_active_pas=target,
        treasury=Treasury(starting_cash),
        capital_policy=capital,
        scaling=fixed_one_mnq(),
        acquisition_policy=AcquisitionPolicy(
            policy_id="fixture_one_at_a_time",
            mode="one_per_decision",
            max_purchases_per_decision=1,
            max_running_evaluations=1,
        ),
        replacement_policy=ReplacementPolicy(
            policy_id="fixture_replace_each_death",
            mode="evaluation_pipeline",
            max_purchases_per_death_event=1,
        ),
        payout_policy=payout,
        path_stress_arm="source_constrained_then_seeded_coin",
        commission_timing="close_only",
        pa_opportunity_selection=selection,
        expected_pa_stream_sha256=selection.accepted_stream_sha256,
        expected_pa_raw_offer_count=selection.raw_count,
    )


def opportunity_map(offers: list[TradeOffer]):
    selection = select_global_one_position(offers)
    return selection, {
        opportunity.offer.trade_key: opportunity
        for opportunity in selection.accepted_opportunities
    }


def run_pa_event(state: Lifecycle, opportunity) -> tuple:
    decision = state.begin_pa_opportunity(opportunity)
    results = state.settle_pa_opportunity(
        decision.opportunity_key,
        decision.exit_at,
    )
    state.assert_integrity()
    return results


def run_shared_evaluation_pa_event(
    state: Lifecycle,
    evaluation_id: str,
    opportunity,
):
    state.begin_evaluation_offer(evaluation_id, opportunity.offer)
    decision = state.begin_pa_opportunity(opportunity)
    pa_results = state.settle_pa_opportunity(
        decision.opportunity_key,
        decision.exit_at,
    )
    evaluation_result = state.settle_evaluation_offer(
        evaluation_id,
        decision.exit_at,
    )
    if evaluation_result.status == "passed":
        state.fund_pending_activation(evaluation_id, decision.exit_at)
    state.assert_integrity()
    return pa_results, evaluation_result


class DeterministicLifecycleFixtureTests(unittest.TestCase):
    def test_n1_evaluation_to_payout_death_and_replacement(self) -> None:
        offers = [
            fixture_offer("eval1_pass", 1, "2026-01-01 10:00:00", "2026-01-01 10:30:00", mae=0, mfe=501.05, gross=501.05),
            fixture_offer("activation_tie_1", 2, "2026-01-01 10:30:00", "2026-01-01 10:31:00", mae=0, mfe=1.05, gross=1.05),
        ]
        for day in range(2, 10):
            offers.append(
                fixture_offer(
                    f"gain_{day - 1:02d}",
                    len(offers) + 1,
                    f"2026-01-{day:02d} 10:00:00",
                    f"2026-01-{day:02d} 10:30:00",
                    mae=-25,
                    mfe=201.05,
                    gross=201.05,
                )
            )
        offers.extend(
            [
                fixture_offer("pa1_death", 11, "2026-01-10 10:00:00", "2026-01-10 10:30:00", mae=-1_000, mfe=0, gross=0),
                fixture_offer("eval2_pass", 12, "2026-01-11 10:00:00", "2026-01-11 10:30:00", mae=0, mfe=501.05, gross=501.05),
                fixture_offer("activation_tie_2", 13, "2026-01-11 10:30:00", "2026-01-11 10:31:00", mae=0, mfe=1.05, gross=1.05),
                fixture_offer("pa2_first", 14, "2026-01-12 10:00:00", "2026-01-12 10:30:00", mae=-25, mfe=101.05, gross=101.05),
            ]
        )
        selection, opportunities = opportunity_map(offers)
        self.assertEqual((len(selection.accepted), len(selection.blocked)), (14, 0))

        state = lifecycle(
            1,
            starting_cash=0,
            capital_mode="through_first_pa",
            selection=selection,
        )
        self.assertEqual(state.plan_growth_and_purchase(at("2026-01-01 01:00:00")), ("eval-1",))
        pa_results, evaluation_result = run_shared_evaluation_pa_event(
            state, "eval-1", opportunities["eval1_pass"]
        )
        self.assertEqual(pa_results, ())
        self.assertEqual(evaluation_result.status, "passed")
        self.assertEqual(state.active_pa_ids, (1,))
        self.assertTrue(state.treasury.external_bridge_closed)

        tie = state.begin_pa_opportunity(opportunities["activation_tie_1"])
        self.assertEqual(tie.account_copy_count, 0)
        state.settle_pa_opportunity(tie.opportunity_key, tie.exit_at)
        for day in range(2, 10):
            results = run_pa_event(state, opportunities[f"gain_{day - 1:02d}"])
            self.assertEqual(len(results), 1)

        payouts = state.execute_session_close_payouts(at("2026-01-09 23:59:00"))
        self.assertEqual(len(payouts), 1)
        self.assertEqual(payouts[0].gross_request_usd, 500.0)
        self.assertEqual(state.pas[1].equity_profit_usd, 1_100.0)
        state.assert_integrity()

        death_results = run_pa_event(state, opportunities["pa1_death"])
        self.assertEqual(sum(not result.survived for result in death_results), 1)
        self.assertFalse(death_results[0].completed_trade_outcome_applied)
        with self.assertRaisesRegex(ValueError, "before growth"):
            state.plan_growth_and_purchase(opportunities["pa1_death"].offer.exit_at)
        self.assertEqual(
            state.plan_death_replacements_and_purchase(
                opportunities["pa1_death"].offer.exit_at,
                1,
            ),
            ("eval-2",),
        )
        self.assertEqual(state.active_pa_ids, ())

        pa_results, evaluation_result = run_shared_evaluation_pa_event(
            state, "eval-2", opportunities["eval2_pass"]
        )
        self.assertEqual(pa_results, ())
        self.assertEqual(evaluation_result.status, "passed")
        self.assertEqual(state.active_pa_ids, (2,))
        tie = state.begin_pa_opportunity(opportunities["activation_tie_2"])
        self.assertEqual(tie.account_copy_count, 0)
        state.settle_pa_opportunity(tie.opportunity_key, tie.exit_at)
        run_pa_event(state, opportunities["pa2_first"])
        state.assert_integrity()

        self.assertEqual(state.global_opportunity_count, 14)
        self.assertEqual(state.account_copy_count, 10)
        self.assertEqual(state.replacement_intent_count, 1)
        self.assertEqual(state.applied_copy_net_pnl_usd, 1_700.0)
        self.assertFalse(state.pas[1].alive)
        self.assertEqual(state.pas[1].equity_profit_usd, 1_100.0)
        self.assertTrue(state.pas[2].alive)
        self.assertEqual(state.pas[2].equity_profit_usd, 100.0)
        self.assertEqual(state.treasury.external_contributions_usd, 160.0)
        self.assertEqual(state.treasury.payout_receipts_usd, 500.0)
        self.assertEqual(state.treasury.fees_paid_usd, 320.0)
        self.assertEqual(state.treasury.cash_usd, 340.0)
        self.assertEqual(state.treasury.reconciliation_error_usd, 0.0)

    def test_n2_common_copies_then_activation_and_payout_divergence(self) -> None:
        offers = [
            fixture_offer("eval1_pass", 1, "2026-01-01 10:00:00", "2026-01-01 10:30:00", mae=0, mfe=501.05, gross=501.05),
            fixture_offer("eval2_pass_pa1_gain", 2, "2026-01-02 10:00:00", "2026-01-02 10:30:00", mae=0, mfe=501.05, gross=501.05),
            fixture_offer("pa2_activation_tie", 3, "2026-01-02 10:30:00", "2026-01-02 10:31:00", mae=0, mfe=1.05, gross=1.05),
        ]
        for day in range(3, 10):
            offers.append(
                fixture_offer(
                    f"joint_{day - 2:02d}",
                    len(offers) + 1,
                    f"2026-01-{day:02d} 10:00:00",
                    f"2026-01-{day:02d} 10:30:00",
                    mae=-25,
                    mfe=201.05,
                    gross=201.05,
                )
            )
        offers.append(
            fixture_offer("divergent_death", 11, "2026-01-10 10:00:00", "2026-01-10 10:30:00", mae=-1_300, mfe=0, gross=0)
        )
        selection, opportunities = opportunity_map(offers)
        self.assertEqual((len(selection.accepted), len(selection.blocked)), (11, 0))

        state = lifecycle(
            2,
            starting_cash=320,
            capital_mode="none",
            selection=selection,
        )
        self.assertEqual(state.plan_growth_and_purchase(at("2026-01-01 01:00:00")), ("eval-1",))
        run_shared_evaluation_pa_event(state, "eval-1", opportunities["eval1_pass"])
        self.assertEqual(state.plan_growth_and_purchase(at("2026-01-01 10:30:00")), ("eval-2",))
        first_shared, _ = run_shared_evaluation_pa_event(
            state,
            "eval-2",
            opportunities["eval2_pass_pa1_gain"],
        )
        self.assertEqual(tuple(result.pa_id for result in first_shared), (1,))
        tie = state.begin_pa_opportunity(opportunities["pa2_activation_tie"])
        self.assertEqual(tie.eligible_pa_ids, (1,))
        state.settle_pa_opportunity(tie.opportunity_key, tie.exit_at)
        for day in range(3, 10):
            result = run_pa_event(state, opportunities[f"joint_{day - 2:02d}"])
            self.assertEqual(tuple(row.pa_id for row in result), (1, 2))

        payouts = state.execute_session_close_payouts(at("2026-01-09 23:59:00"))
        self.assertEqual(tuple(record.pa_id for record in payouts), (1,))
        self.assertEqual(state.pas[1].equity_profit_usd, 1_400.0)
        self.assertEqual(state.pas[2].equity_profit_usd, 1_400.0)
        death_results = run_pa_event(state, opportunities["divergent_death"])
        self.assertEqual(
            tuple((result.pa_id, result.survived) for result in death_results),
            ((1, False), (2, True)),
        )
        self.assertEqual(
            state.plan_death_replacements_and_purchase(
                opportunities["divergent_death"].offer.exit_at,
                1,
            ),
            ("eval-3",),
        )
        state.assert_integrity()

        self.assertEqual(
            tuple(decision.account_copy_count for decision in state.copy_decisions),
            (0, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2),
        )
        self.assertEqual(state.global_opportunity_count, 11)
        self.assertEqual(state.account_copy_count, 18)
        self.assertEqual(state.replacement_intent_count, 1)
        self.assertEqual(state.applied_copy_net_pnl_usd, 3_298.95)
        self.assertFalse(state.pas[1].alive)
        self.assertEqual(state.pas[1].equity_profit_usd, 1_400.0)
        self.assertTrue(state.pas[2].alive)
        self.assertEqual(state.pas[2].equity_profit_usd, 1_398.95)
        self.assertEqual(state.active_pa_ids, (2,))
        self.assertEqual(tuple(state.evaluations), ("eval-3",))
        self.assertEqual(state.pipeline_state.capacity_commitments, 2)
        self.assertEqual(state.treasury.starting_cash_usd, 320.0)
        self.assertEqual(state.treasury.external_contributions_usd, 0.0)
        self.assertEqual(state.treasury.payout_receipts_usd, 500.0)
        self.assertEqual(state.treasury.fees_paid_usd, 355.0)
        self.assertEqual(state.treasury.cash_usd, 465.0)

    def test_bound_stream_rejects_reselection_out_of_order_and_replay(self) -> None:
        offers = [
            fixture_offer("accepted_1", 1, "2026-02-01 10:00:00", "2026-02-01 11:00:00", mae=0, mfe=11.05, gross=11.05),
            fixture_offer("blocked", 2, "2026-02-01 10:30:00", "2026-02-01 10:45:00", mae=0, mfe=11.05, gross=11.05),
            fixture_offer("accepted_2", 3, "2026-02-01 11:00:00", "2026-02-01 11:30:00", mae=0, mfe=11.05, gross=11.05),
        ]
        selection = select_global_one_position(offers)
        state = lifecycle(
            1,
            starting_cash=0,
            capital_mode="none",
            selection=selection,
        )
        blocked_reselected = select_global_one_position(
            [selection.blocked[0]]
        ).accepted_opportunities[0]
        with self.assertRaisesRegex(ValueError, "bound global stream"):
            state.begin_pa_opportunity(blocked_reselected)
        with self.assertRaisesRegex(ValueError, "bound global stream"):
            state.begin_pa_opportunity(selection.accepted_opportunities[1])

        first = selection.accepted_opportunities[0]
        state.begin_pa_opportunity(first)
        with self.assertRaisesRegex(ValueError, "prior PA copy batch"):
            state.begin_pa_opportunity(selection.accepted_opportunities[1])
        state.settle_pa_opportunity(first.offer.trade_key, first.offer.exit_at)
        with self.assertRaisesRegex(ValueError, "bound global stream"):
            state.begin_pa_opportunity(first)
        second = selection.accepted_opportunities[1]
        state.begin_pa_opportunity(second)
        state.settle_pa_opportunity(second.offer.trade_key, second.offer.exit_at)
        self.assertEqual(state.global_opportunity_count, 2)

    def test_zero_duration_trade_has_explicit_entry_then_exit_suborder(self) -> None:
        offers = [
            fixture_offer("eval1_pass", 1, "2026-02-02 10:00:00", "2026-02-02 10:30:00", mae=0, mfe=501.05, gross=501.05),
            fixture_offer("zero_shared", 2, "2026-02-02 11:00:00", "2026-02-02 11:00:00", mae=0, mfe=501.05, gross=501.05),
        ]
        selection, opportunities = opportunity_map(offers)
        state = lifecycle(
            2,
            starting_cash=320,
            capital_mode="none",
            selection=selection,
        )
        state.plan_growth_and_purchase(at("2026-02-02 01:00:00"))
        run_shared_evaluation_pa_event(
            state,
            "eval-1",
            opportunities["eval1_pass"],
        )
        state.plan_growth_and_purchase(at("2026-02-02 10:30:00"))
        pa_results, evaluation_result = run_shared_evaluation_pa_event(
            state,
            "eval-2",
            opportunities["zero_shared"],
        )
        self.assertEqual(tuple(result.pa_id for result in pa_results), (1,))
        self.assertEqual(evaluation_result.status, "passed")
        self.assertEqual(state.active_pa_ids, (1, 2))
        zero_phases = tuple(
            event.phase for event in state.audit if event.reference == "zero_shared"
        )
        self.assertEqual(
            zero_phases,
            (
                "zero_duration_evaluation_entry",
                "zero_duration_pa_entry",
                "zero_duration_pa_exit",
                "zero_duration_evaluation_exit",
            ),
        )

    def test_due_pa_exit_precedes_evaluation_exit_and_later_events(self) -> None:
        selection, opportunities = opportunity_map(
            [
                fixture_offer("shared_pass", 1, "2026-02-06 10:00:00", "2026-02-06 10:30:00", mae=0, mfe=501.05, gross=501.05)
            ]
        )
        state = lifecycle(
            1,
            starting_cash=160,
            capital_mode="none",
            selection=selection,
        )
        state.plan_growth_and_purchase(at("2026-02-06 01:00:00"))
        opportunity = opportunities["shared_pass"]
        state.begin_evaluation_offer("eval-1", opportunity.offer)
        decision = state.begin_pa_opportunity(opportunity)
        with self.assertRaisesRegex(ValueError, "due trade exit"):
            state.settle_evaluation_offer("eval-1", decision.exit_at)
        with self.assertRaisesRegex(ValueError, "due trade exit"):
            state.execute_session_close_payouts(
                decision.exit_at + timedelta(minutes=1)
            )
        state.settle_pa_opportunity(decision.opportunity_key, decision.exit_at)
        result = state.settle_evaluation_offer("eval-1", decision.exit_at)
        self.assertEqual(result.status, "passed")
        state.fund_pending_activation("eval-1", decision.exit_at)
        self.assertEqual(state.active_pa_ids, (1,))
        state.assert_integrity()

    def test_correlated_deaths_preserve_sequential_replacement_backlog(self) -> None:
        offers = [
            fixture_offer("eval1_pass", 1, "2026-02-10 10:00:00", "2026-02-10 10:30:00", mae=0, mfe=501.05, gross=501.05),
            fixture_offer("eval2_pass", 2, "2026-02-11 10:00:00", "2026-02-11 10:30:00", mae=0, mfe=501.05, gross=501.05),
            fixture_offer("both_die", 3, "2026-02-12 10:00:00", "2026-02-12 10:30:00", mae=-1_501.0, mfe=0, gross=0),
            fixture_offer("eval3_pass", 4, "2026-02-13 10:00:00", "2026-02-13 10:30:00", mae=0, mfe=501.05, gross=501.05),
        ]
        selection, opportunities = opportunity_map(offers)
        state = lifecycle(
            2,
            starting_cash=515,
            capital_mode="none",
            selection=selection,
        )
        state.plan_growth_and_purchase(at("2026-02-10 01:00:00"))
        run_shared_evaluation_pa_event(state, "eval-1", opportunities["eval1_pass"])
        state.plan_growth_and_purchase(at("2026-02-10 10:30:00"))
        run_shared_evaluation_pa_event(state, "eval-2", opportunities["eval2_pass"])
        deaths = run_pa_event(state, opportunities["both_die"])
        self.assertEqual(sum(not result.survived for result in deaths), 2)
        self.assertEqual(state.unprocessed_pa_death_count, 2)

        self.assertEqual(
            state.plan_death_replacements_and_purchase(
                opportunities["both_die"].offer.exit_at,
                2,
            ),
            ("eval-3",),
        )
        self.assertEqual(state.unprocessed_pa_death_count, 1)
        self.assertFalse(state.death_replacement_planning_due)
        run_shared_evaluation_pa_event(state, "eval-3", opportunities["eval3_pass"])
        with self.assertRaisesRegex(ValueError, "before growth"):
            state.plan_growth_and_purchase(opportunities["eval3_pass"].offer.exit_at)
        self.assertEqual(
            state.plan_death_replacements_and_purchase(
                opportunities["eval3_pass"].offer.exit_at,
                1,
            ),
            ("eval-4",),
        )
        self.assertEqual(state.unprocessed_pa_death_count, 0)
        self.assertEqual(state.replacement_intent_count, 2)
        self.assertEqual(state.active_pa_ids, (3,))
        self.assertEqual(tuple(state.evaluations), ("eval-4",))
        self.assertEqual(state.treasury.cash_usd, 0.0)
        state.assert_integrity()

    def test_unfunded_replacement_attempt_does_not_pause_pa_stream(self) -> None:
        offers = [
            fixture_offer("eval1_pass", 1, "2026-03-01 10:00:00", "2026-03-01 10:30:00", mae=0, mfe=501.05, gross=501.05),
        ]
        for day in range(2, 10):
            offers.append(
                fixture_offer(
                    f"pa1_gain_{day:02d}",
                    len(offers) + 1,
                    f"2026-03-{day:02d} 10:00:00",
                    f"2026-03-{day:02d} 10:30:00",
                    mae=-25,
                    mfe=201.05,
                    gross=201.05,
                )
            )
        offers.extend(
            [
                fixture_offer("eval2_pass", 10, "2026-03-10 10:00:00", "2026-03-10 10:30:00", mae=0, mfe=501.05, gross=501.05),
                fixture_offer("pa2_death", 11, "2026-03-11 10:00:00", "2026-03-11 10:30:00", mae=-1_550, mfe=0, gross=0),
                fixture_offer("stream_continues", 12, "2026-03-12 10:00:00", "2026-03-12 10:30:00", mae=-25, mfe=101.05, gross=101.05),
            ]
        )
        selection, opportunities = opportunity_map(offers)
        state = lifecycle(
            2,
            starting_cash=320,
            capital_mode="none",
            selection=selection,
        )

        state.plan_growth_and_purchase(at("2026-03-01 01:00:00"))
        run_shared_evaluation_pa_event(
            state,
            "eval-1",
            opportunities["eval1_pass"],
        )
        self.assertEqual(
            state.plan_growth_and_purchase(at("2026-03-01 10:30:00")),
            ("eval-2",),
        )
        for day in range(2, 10):
            run_pa_event(state, opportunities[f"pa1_gain_{day:02d}"])
        run_shared_evaluation_pa_event(
            state,
            "eval-2",
            opportunities["eval2_pass"],
        )
        self.assertEqual(state.active_pa_ids, (1, 2))
        self.assertEqual(state.treasury.cash_usd, 0.0)

        deaths = run_pa_event(state, opportunities["pa2_death"])
        self.assertEqual(
            tuple((result.pa_id, result.survived) for result in deaths),
            ((1, True), (2, False)),
        )
        death_at = opportunities["pa2_death"].offer.exit_at
        self.assertEqual(
            state.plan_death_replacements_and_purchase(death_at, 1),
            (),
        )
        self.assertEqual(state.unprocessed_pa_death_count, 1)
        self.assertFalse(state.death_replacement_planning_due)
        with self.assertRaisesRegex(ValueError, "before growth"):
            state.plan_growth_and_purchase(death_at + timedelta(minutes=1))

        continued = run_pa_event(state, opportunities["stream_continues"])
        self.assertEqual(tuple(result.pa_id for result in continued), (1,))
        payout_at = at("2026-03-12 23:59:00")
        payouts = state.execute_session_close_payouts(payout_at)
        self.assertEqual(tuple(record.pa_id for record in payouts), (1,))
        self.assertEqual(state.treasury.cash_usd, 500.0)
        self.assertEqual(
            state.plan_death_replacements_and_purchase(payout_at, 1),
            ("eval-3",),
        )
        self.assertEqual(state.unprocessed_pa_death_count, 0)
        self.assertEqual(state.replacement_intent_count, 1)
        self.assertEqual(state.treasury.cash_usd, 465.0)
        self.assertEqual(
            tuple(
                event.event_type
                for event in state.audit
                if event.reference == "eval-3"
            ),
            ("evaluation_purchase_unfunded", "evaluation_purchased"),
        )
        state.assert_integrity()

    def test_session_close_payout_rejects_other_clock_times(self) -> None:
        selection = select_global_one_position(
            [
                fixture_offer("future", 1, "2026-07-02 10:00:00", "2026-07-02 10:30:00", mae=0, mfe=1.05, gross=1.05)
            ]
        )
        state = lifecycle(
            1,
            starting_cash=0,
            capital_mode="none",
            selection=selection,
        )
        with self.assertRaisesRegex(ValueError, "exactly 23:59"):
            state.execute_session_close_payouts(at("2026-07-01 22:00:00"))
        state.assert_integrity()

    def test_open_copy_blocks_fixture_payout_without_mutation(self) -> None:
        offers = [
            fixture_offer("eval_pass", 1, "2026-02-03 10:00:00", "2026-02-03 10:30:00", mae=0, mfe=501.05, gross=501.05),
            fixture_offer("open_copy", 2, "2026-02-04 10:00:00", "2026-02-05 10:00:00", mae=0, mfe=101.05, gross=101.05),
        ]
        selection, opportunities = opportunity_map(offers)
        state = lifecycle(
            1,
            starting_cash=160,
            capital_mode="none",
            selection=selection,
        )
        state.plan_growth_and_purchase(at("2026-02-03 01:00:00"))
        run_shared_evaluation_pa_event(state, "eval-1", opportunities["eval_pass"])
        account = state.pas[1]
        account.equity_profit_usd = 2_600.0
        account.peak_profit_usd = 2_600.0
        account.liquidation_floor_profit_usd = 100.0
        account.payout_period_daily_pnl_usd = {
            (at("2026-01-20 10:00:00") + timedelta(days=offset)).date(): 100.0
            for offset in range(8)
        }
        state.begin_pa_opportunity(opportunities["open_copy"])
        snapshot = (
            account.equity_profit_usd,
            account.payout_count,
            dict(account.payout_period_daily_pnl_usd),
            state.treasury.cash_usd,
        )
        with self.assertRaisesRegex(ValueError, "outstanding PA copy"):
            state.execute_session_close_payouts(at("2026-02-04 23:59:00"))
        self.assertEqual(
            snapshot,
            (
                account.equity_profit_usd,
                account.payout_count,
                account.payout_period_daily_pnl_usd,
                state.treasury.cash_usd,
            ),
        )

    def test_invalid_renewal_does_not_spend_treasury_cash(self) -> None:
        selection = select_global_one_position(
            [
                fixture_offer("future", 1, "2026-04-01 10:00:00", "2026-04-01 10:30:00", mae=0, mfe=1.05, gross=1.05)
            ]
        )
        state = lifecycle(
            1,
            starting_cash=70,
            capital_mode="none",
            selection=selection,
        )
        state.plan_growth_and_purchase(at("2026-03-01 01:00:00"))
        before = (
            state.treasury.cash_usd,
            state.treasury.fees_paid_usd,
            len(state.treasury.ledger),
            state.evaluations["eval-1"].cycle_number,
        )
        with self.assertRaisesRegex(ValueError, "exact cycle boundary"):
            state.fund_and_renew_evaluation(
                "eval-1",
                at("2026-03-30 01:00:00"),
            )
        self.assertEqual(
            before,
            (
                state.treasury.cash_usd,
                state.treasury.fees_paid_usd,
                len(state.treasury.ledger),
                state.evaluations["eval-1"].cycle_number,
            ),
        )

    def test_unfunded_renewal_closes_evaluation_and_releases_capacity(self) -> None:
        selection = select_global_one_position(
            [
                fixture_offer("future", 1, "2026-06-01 10:00:00", "2026-06-01 10:30:00", mae=0, mfe=1.05, gross=1.05)
            ]
        )
        state = lifecycle(
            1,
            starting_cash=35,
            capital_mode="none",
            selection=selection,
        )
        state.plan_growth_and_purchase(at("2026-04-01 01:00:00"))
        due_at = state.evaluations["eval-1"].cycle_due_at(state.evaluation_rules)
        treasury_before = (
            state.treasury.cash_usd,
            state.treasury.external_contributions_usd,
            state.treasury.fees_paid_usd,
            tuple(state.treasury.ledger),
        )

        self.assertFalse(state.fund_and_renew_evaluation("eval-1", due_at))

        self.assertNotIn("eval-1", state.evaluations)
        self.assertEqual(state.pipeline_state.capacity_commitments, 0)
        self.assertEqual(state.pipeline_state.open_slots, 1)
        self.assertEqual(
            treasury_before,
            (
                state.treasury.cash_usd,
                state.treasury.external_contributions_usd,
                state.treasury.fees_paid_usd,
                tuple(state.treasury.ledger),
            ),
        )
        self.assertEqual(
            (state.audit[-1].event_type, state.audit[-1].reference),
            ("evaluation_renewal_unfunded", "eval-1"),
        )
        state.assert_integrity()

    def test_only_one_purchase_decision_is_allowed_per_timestamp(self) -> None:
        selection = select_global_one_position(
            [
                fixture_offer("future", 1, "2026-08-01 10:00:00", "2026-08-01 10:30:00", mae=0, mfe=1.05, gross=1.05)
            ]
        )
        state = lifecycle(
            3,
            starting_cash=105,
            capital_mode="none",
            selection=selection,
        )
        state.acquisition_policy = AcquisitionPolicy(
            policy_id="fixture_unbounded_running_evaluations",
            mode="one_per_decision",
            max_purchases_per_decision=1,
            max_running_evaluations=None,
        )
        decision_at = at("2026-06-01 01:00:00")

        self.assertEqual(state.plan_growth_and_purchase(decision_at), ("eval-1",))
        with self.assertRaisesRegex(ValueError, "per timestamp"):
            state.plan_growth_and_purchase(decision_at)
        self.assertEqual(tuple(state.evaluations), ("eval-1",))
        self.assertEqual(state.treasury.cash_usd, 70.0)

        self.assertEqual(
            state.plan_growth_and_purchase(decision_at + timedelta(seconds=1)),
            ("eval-2",),
        )
        self.assertEqual(tuple(state.evaluations), ("eval-1", "eval-2"))
        self.assertEqual(state.treasury.cash_usd, 35.0)
        state.assert_integrity()

    def test_payout_and_treasury_receipt_roll_back_together(self) -> None:
        selection, opportunities = opportunity_map(
            [
                fixture_offer("eval_pass", 1, "2026-04-02 10:00:00", "2026-04-02 10:30:00", mae=0, mfe=501.05, gross=501.05)
            ]
        )
        state = lifecycle(
            1,
            starting_cash=160,
            capital_mode="none",
            selection=selection,
        )
        state.plan_growth_and_purchase(at("2026-04-02 01:00:00"))
        run_shared_evaluation_pa_event(state, "eval-1", opportunities["eval_pass"])
        account = state.pas[1]
        account.equity_profit_usd = 2_600.0
        account.peak_profit_usd = 2_600.0
        account.liquidation_floor_profit_usd = 100.0
        account.payout_period_daily_pnl_usd = {
            (at("2026-03-20 10:00:00") + timedelta(days=offset)).date(): 100.0
            for offset in range(8)
        }
        snapshot = (
            account.equity_profit_usd,
            account.payout_count,
            account.cumulative_gross_payouts_usd,
            account.cumulative_net_payouts_usd,
            dict(account.payout_period_daily_pnl_usd),
            state.treasury.cash_usd,
            state.treasury.payout_receipts_usd,
            len(state.treasury.ledger),
            len(state.audit),
        )
        original_receive = Treasury.receive_payout

        def receive_then_fail(treasury, event_at, amount_usd, reference):
            original_receive(treasury, event_at, amount_usd, reference)
            raise RuntimeError("injected receipt failure")

        with patch.object(Treasury, "receive_payout", new=receive_then_fail):
            with self.assertRaisesRegex(RuntimeError, "injected receipt failure"):
                state.execute_session_close_payouts(at("2026-04-02 23:59:00"))
        self.assertEqual(
            snapshot,
            (
                account.equity_profit_usd,
                account.payout_count,
                account.cumulative_gross_payouts_usd,
                account.cumulative_net_payouts_usd,
                account.payout_period_daily_pnl_usd,
                state.treasury.cash_usd,
                state.treasury.payout_receipts_usd,
                len(state.treasury.ledger),
                len(state.audit),
            ),
        )
        self.assertEqual(state.payouts, [])


class EvaluationMechanicsContractTests(unittest.TestCase):
    def account(self, identity: str = "eval") -> EvaluationAccount:
        purchased = at("2026-05-01 01:00:00")
        return EvaluationAccount(
            evaluation_id=identity,
            purchased_at=purchased,
            cycle_started_at=purchased,
        )

    def test_ambiguous_path_arm_changes_evaluation_pass_to_failure(self) -> None:
        trade = fixture_offer(
            "ambiguous_eval",
            1,
            "2026-05-02 10:00:00",
            "2026-05-02 10:30:00",
            mae=-400.0,
            mfe=600.0,
            gross=501.05,
        )
        self.assertEqual(trade.intratrade_path_status, "ambiguous")
        statuses = {}
        for order in ("mae_first", "mfe_first"):
            account = self.account(order)
            begin_evaluation_trade(account, trade)
            statuses[order] = settle_evaluation_trade(
                account,
                event_at=trade.exit_at,
                path_order=order,
            ).status
        self.assertEqual(statuses, {"mae_first": "passed", "mfe_first": "failed"})

    def test_threshold_touch_and_cycle_boundaries_are_exact(self) -> None:
        rules = EvaluationRules()
        touch = fixture_offer(
            "touch",
            1,
            "2026-05-02 10:00:00",
            "2026-05-02 10:30:00",
            mae=-498.95,
            mfe=0.0,
            gross=0.0,
        )
        account = self.account()
        begin_evaluation_trade(account, touch, rules)
        result = settle_evaluation_trade(
            account,
            event_at=touch.exit_at,
            path_order="mae_first",
            rules=rules,
        )
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.completed_trade_outcome_applied)

        due_account = self.account("due")
        due = due_account.cycle_due_at(rules)
        at_due = fixture_offer(
            "at_due",
            2,
            due.strftime("%Y-%m-%d %H:%M:%S"),
            due.strftime("%Y-%m-%d %H:%M:%S"),
            mae=0.0,
            mfe=1.05,
            gross=1.05,
        )
        with self.assertRaisesRegex(ValueError, "outside the funded cycle"):
            begin_evaluation_trade(due_account, at_due, rules)

    def test_renewal_carries_active_state_and_resets_failure(self) -> None:
        rules = EvaluationRules()
        active = self.account("active")
        active.profit_usd = 100.0
        active.peak_profit_usd = 200.0
        active.floor_profit_usd = -1_300.0
        active.trading_days.add(at("2026-05-02 10:00:00").date())
        renew_evaluation(active, active.cycle_due_at(rules), rules)
        self.assertEqual(
            (active.cycle_number, active.status, active.profit_usd, active.peak_profit_usd),
            (2, "active", 100.0, 200.0),
        )

        failed = self.account("failed")
        failed.status = "failed"
        failed.profit_usd = -200.0
        failed.peak_profit_usd = 50.0
        failed.floor_profit_usd = -1_450.0
        failed.trading_days.add(at("2026-05-02 10:00:00").date())
        renew_evaluation(failed, failed.cycle_due_at(rules), rules)
        self.assertEqual(
            (
                failed.cycle_number,
                failed.status,
                failed.profit_usd,
                failed.peak_profit_usd,
                failed.floor_profit_usd,
                failed.trading_days,
            ),
            (2, "active", 0.0, 0.0, -1_500.0, set()),
        )


class PayoutCandidateContractTests(unittest.TestCase):
    def policies(self):
        return {
            policy.policy_id: policy
            for policy in load_payout_policies(
                ROOT / "config" / "payout_policies.json"
            )
        }

    def eligible_history(self) -> dict:
        return {
            (at("2026-06-01 10:00:00") + timedelta(days=offset)).date(): 100.0
            for offset in range(8)
        }

    def test_all_six_candidates_choose_distinct_rule_compliant_amounts(self) -> None:
        policies = self.policies()
        history = {
            (at("2026-01-02 10:00:00") + timedelta(days=offset)).date(): 100.0
            for offset in range(8)
        }
        first = PAAccount(
            1,
            at("2026-01-01 10:00:00"),
            equity_profit_usd=2_600.0,
            peak_profit_usd=2_600.0,
            liquidation_floor_profit_usd=100.0,
            payout_period_daily_pnl_usd=dict(history),
        )
        expected_first = {
            "minimum_500_always": 500.0,
            "maximum_always": 1_500.0,
            "rush_to_uncapped": 500.0,
            "cap_maximizer": 1_500.0,
            "preserve_safety_net": 1_000.0,
            "half_of_maximum": 750.0,
        }
        self.assertEqual(
            {
                policy_id: choose_payout_amount(first, policy)
                for policy_id, policy in policies.items()
            },
            expected_first,
        )

        sixth = PAAccount(
            2,
            at("2026-01-01 10:00:00"),
            equity_profit_usd=5_000.0,
            peak_profit_usd=5_000.0,
            liquidation_floor_profit_usd=100.0,
            payout_period_daily_pnl_usd=dict(history),
            payout_count=5,
        )
        expected_sixth = {
            "minimum_500_always": 500.0,
            "maximum_always": 4_899.99,
            "rush_to_uncapped": 4_899.99,
            "cap_maximizer": 4_899.99,
            "preserve_safety_net": 3_400.0,
            "half_of_maximum": 2_449.99,
        }
        self.assertEqual(
            {
                policy_id: choose_payout_amount(sixth, policy)
                for policy_id, policy in policies.items()
            },
            expected_sixth,
        )

    def test_day_profit_safety_net_and_cap_boundaries(self) -> None:
        maximum = self.policies()["maximum_always"]
        base = at("2026-06-01 10:00:00")
        seven_days = {
            (base + timedelta(days=offset)).date(): 50.0 if offset < 5 else 0.0
            for offset in range(7)
        }
        account = PAAccount(
            1,
            base - timedelta(days=1),
            equity_profit_usd=2_600.0,
            peak_profit_usd=2_600.0,
            liquidation_floor_profit_usd=100.0,
            payout_period_daily_pnl_usd=seven_days,
        )
        self.assertIsNone(choose_payout_amount(account, maximum))
        account.payout_period_daily_pnl_usd[
            (base + timedelta(days=7)).date()
        ] = 49.99
        self.assertEqual(choose_payout_amount(account, maximum), 1_500.0)
        account.payout_period_daily_pnl_usd = {
            (base + timedelta(days=offset)).date(): 50.0 if offset < 4 else 49.99
            for offset in range(8)
        }
        self.assertIsNone(choose_payout_amount(account, maximum))
        account.payout_period_daily_pnl_usd[
            (base + timedelta(days=4)).date()
        ] = 50.0
        self.assertEqual(choose_payout_amount(account, maximum), 1_500.0)

        account.payout_period_daily_pnl_usd = self.eligible_history()
        account.equity_profit_usd = 1_600.0
        account.peak_profit_usd = 1_600.0
        account.payout_count = 2
        self.assertEqual(maximum_eligible_gross(account), 500.0)
        account.payout_count = 3
        self.assertEqual(maximum_eligible_gross(account), 1_499.99)
        account.equity_profit_usd = 5_000.0
        account.peak_profit_usd = 5_000.0
        account.payout_count = 4
        self.assertEqual(maximum_eligible_gross(account), 1_500.0)
        account.payout_count = 5
        self.assertEqual(maximum_eligible_gross(account), 4_899.99)

    def test_split_crossing_period_reset_and_failed_atomic_preflight(self) -> None:
        maximum = self.policies()["maximum_always"]
        account = PAAccount(
            1,
            at("2026-06-01 10:00:00"),
            equity_profit_usd=2_600.0,
            peak_profit_usd=2_600.0,
            liquidation_floor_profit_usd=100.0,
            payout_period_daily_pnl_usd=self.eligible_history(),
            cumulative_gross_payouts_usd=24_900.0,
            cumulative_net_payouts_usd=24_900.0,
        )
        record = execute_atomic_payout_if_eligible(
            account,
            at("2026-06-10 23:59:00"),
            maximum,
        )
        assert record is not None
        self.assertEqual(
            (record.gross_request_usd, record.treasury_receipt_usd),
            (1_500.0, 1_360.0),
        )
        self.assertEqual(account.payout_period_daily_pnl_usd, {})
        self.assertEqual(account.cumulative_gross_payouts_usd, 26_400.0)

        unsafe = PAAccount(
            2,
            at("2026-06-01 10:00:00"),
            equity_profit_usd=2_600.0,
            peak_profit_usd=2_600.0,
            liquidation_floor_profit_usd=2_200.0,
            payout_period_daily_pnl_usd=self.eligible_history(),
        )
        snapshot = (
            unsafe.equity_profit_usd,
            unsafe.payout_count,
            unsafe.cumulative_gross_payouts_usd,
            dict(unsafe.payout_period_daily_pnl_usd),
        )
        with self.assertRaisesRegex(RuntimeError, "would breach"):
            execute_atomic_payout_if_eligible(
                unsafe,
                at("2026-06-10 23:59:00"),
                maximum,
            )
        self.assertEqual(
            snapshot,
            (
                unsafe.equity_profit_usd,
                unsafe.payout_count,
                unsafe.cumulative_gross_payouts_usd,
                unsafe.payout_period_daily_pnl_usd,
            ),
        )

    def test_record_construction_failure_leaves_pa_unchanged(self) -> None:
        maximum = self.policies()["maximum_always"]
        account = PAAccount(
            3,
            at("2026-06-01 10:00:00"),
            equity_profit_usd=2_600.0,
            peak_profit_usd=2_600.0,
            liquidation_floor_profit_usd=100.0,
            payout_period_daily_pnl_usd=self.eligible_history(),
        )
        snapshot = (
            account.equity_profit_usd,
            account.payout_count,
            account.cumulative_gross_payouts_usd,
            account.cumulative_net_payouts_usd,
            dict(account.payout_period_daily_pnl_usd),
        )
        with patch(
            "milky_cow.payouts.PayoutRecord",
            side_effect=ValueError("synthetic record failure"),
        ):
            with self.assertRaisesRegex(ValueError, "synthetic record failure"):
                execute_atomic_payout_if_eligible(
                    account,
                    at("2026-06-10 23:59:00"),
                    maximum,
                )
        self.assertEqual(
            snapshot,
            (
                account.equity_profit_usd,
                account.payout_count,
                account.cumulative_gross_payouts_usd,
                account.cumulative_net_payouts_usd,
                account.payout_period_daily_pnl_usd,
            ),
        )


if __name__ == "__main__":
    unittest.main()
