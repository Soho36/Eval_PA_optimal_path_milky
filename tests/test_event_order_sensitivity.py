from __future__ import annotations

from datetime import datetime
import unittest

from milky_cow.contracts import (
    AcquisitionPolicy,
    ReplacementPolicy,
    ScalingLevel,
    ScalingSchedule,
)
from milky_cow.inputs import (
    OpportunitySelection,
    TradeOffer,
    get_timezone,
)
from milky_cow.lifecycle import Lifecycle, event_order_phase_ranks
from milky_cow.payouts import PayoutPolicy, PayoutRule
from milky_cow.treasury import ExternalCapitalPolicy, Treasury


ZONE = get_timezone("Europe/Tallinn")
CANONICAL_ORDER = (
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
)
SPEND_BEFORE_PAYOUT_ORDER = (
    "pa_exit",
    "evaluation_exit",
    "zero_duration_evaluation_entry",
    "zero_duration_pa_entry",
    "zero_duration_pa_exit",
    "zero_duration_evaluation_exit",
    "renewal",
    "activation",
    "purchase",
    "payout",
    "evaluation_entry",
    "pa_entry",
)


def at(label: str) -> datetime:
    return datetime.strptime(label, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZONE)


def lifecycle(event_order_mode: str | None = None) -> Lifecycle:
    offer = TradeOffer(
        trade_key="event_order_fixture",
        strategy_id="event_order_fixture",
        window_id="10-11",
        window_order=10,
        source_row=1,
        ticket=1,
        source_entry_label="2026-01-02 10:00:00",
        source_exit_label="2026-01-02 10:30:00",
        source_timezone_rule="Europe/Tallinn:fixture",
        entry_at=at("2026-01-02 10:00:00"),
        exit_at=at("2026-01-02 10:30:00"),
        mae_usd_per_mnq=0.0,
        mfe_usd_per_mnq=0.0,
        gross_pnl_usd_per_mnq=0.0,
        candle_range=1.0,
        commission_usd_per_mnq=0.0,
        resolved_path_order="mae_first",
        source_file_sha256="0" * 64,
    )
    selection = OpportunitySelection((offer,), ())
    kwargs = {}
    if event_order_mode is not None:
        kwargs["event_order_mode"] = event_order_mode
    return Lifecycle(
        target_active_pas=1,
        treasury=Treasury(0.0),
        capital_policy=ExternalCapitalPolicy(
            policy_id="fixture_none",
            mode="none",
            permitted_uses=(),
            lifetime_cap_usd=0.0,
            contribution_timing="just_in_time_exact_shortfall",
            close_event="never",
            reopens=False,
        ),
        scaling=ScalingSchedule(
            policy_id="fixture_one_mnq",
            scope="per_account",
            threshold_metric="realized_balance_usd",
            levels=(ScalingLevel(None, 1),),
            threshold_operator="greater_than_or_equal",
            decision_time="entry_before_trade_after_prior_same_timestamp_events",
            downscale_rule="immediate",
            synchronized_aggregation=None,
            maximum_mnq=1,
            outcome_scaling="linear_per_mnq",
        ),
        acquisition_policy=AcquisitionPolicy(
            policy_id="fixture_none",
            mode="none",
            max_purchases_per_decision=1,
            max_running_evaluations=1,
        ),
        replacement_policy=ReplacementPolicy(
            policy_id="fixture_never",
            mode="never",
            max_purchases_per_death_event=1,
        ),
        payout_policy=PayoutPolicy(
            policy_id="fixture_minimum",
            early_rule=PayoutRule("minimum"),
        ),
        path_stress_arm="source_constrained_then_seeded_coin",
        commission_timing="close_only",
        pa_opportunity_selection=selection,
        expected_pa_stream_sha256=selection.accepted_stream_sha256,
        expected_pa_raw_offer_count=selection.raw_count,
        **kwargs,
    )


class EventOrderSensitivityTests(unittest.TestCase):
    def test_canonical_default_remains_the_declared_order(self) -> None:
        state = lifecycle()

        self.assertEqual(
            state.event_order_mode,
            "canonical_settle_realize_spend_commit",
        )
        self.assertEqual(state.event_order_phases, CANONICAL_ORDER)
        self.assertEqual(
            tuple(
                phase
                for phase, _ in sorted(
                    event_order_phase_ranks(state.event_order_mode).items(),
                    key=lambda item: item[1],
                )
            ),
            CANONICAL_ORDER,
        )

    def test_spend_before_payout_is_an_executable_deterministic_arm(self) -> None:
        state = lifecycle("spend_before_payout")
        event_at = at("2026-01-03 23:59:00")

        self.assertEqual(state.event_order_phases, SPEND_BEFORE_PAYOUT_ORDER)
        for phase in state.event_order_phases:
            state._record(event_at, phase, "fixture_phase", phase)

        self.assertEqual(
            tuple(event.phase for event in state.audit),
            SPEND_BEFORE_PAYOUT_ORDER,
        )
        state.assert_integrity()

    def test_each_arm_rejects_the_other_cash_order(self) -> None:
        event_at = at("2026-01-03 23:59:00")

        canonical = lifecycle()
        canonical._record(event_at, "purchase", "fixture_phase", "purchase")
        with self.assertRaisesRegex(ValueError, "phase order regressed"):
            canonical._record(event_at, "payout", "fixture_phase", "payout")

        sensitivity = lifecycle("spend_before_payout")
        sensitivity._record(event_at, "payout", "fixture_phase", "payout")
        with self.assertRaisesRegex(ValueError, "phase order regressed"):
            sensitivity._record(event_at, "purchase", "fixture_phase", "purchase")

    def test_unknown_event_order_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "event-order mode"):
            lifecycle("random_order")


if __name__ == "__main__":
    unittest.main()
