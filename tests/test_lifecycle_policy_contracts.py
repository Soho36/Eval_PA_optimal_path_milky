from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import unittest

from milky_cow.contracts import (
    AcquisitionPolicy,
    BookPipelineState,
    ReplacementPolicy,
    ScalingLevel,
    ScalingSchedule,
    plan_evaluation_purchase_intents,
)
from milky_cow.inputs import get_timezone
from milky_cow.treasury import ExternalCapitalPolicy, Treasury


ROOT = Path(__file__).resolve().parents[1]
ZONE = get_timezone("Europe/Tallinn")


def at(label: str) -> datetime:
    return datetime.strptime(label, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZONE)


def acquisition(
    mode: str = "fill_open_slots",
    *,
    max_event: int = 20,
    max_running: int | None = 20,
    cadence_days: int | None = None,
) -> AcquisitionPolicy:
    return AcquisitionPolicy(
        policy_id=f"fixture_{mode}",
        mode=mode,
        max_purchases_per_decision=max_event,
        max_running_evaluations=max_running,
        cadence_days=cadence_days,
    )


def replacement(mode: str = "evaluation_pipeline") -> ReplacementPolicy:
    return ReplacementPolicy(
        policy_id=f"fixture_{mode}",
        mode=mode,
        max_purchases_per_death_event=20,
    )


class AcquisitionAndReplacementContractTests(unittest.TestCase):
    def test_pipeline_commitments_prevent_target_overshoot(self) -> None:
        state = BookPipelineState(
            target_active_pas=3,
            active_pa_ids=(1,),
            target_accounting="active_plus_running_and_pending",
            running_evaluation_ids=("eval-1",),
        )
        intents = plan_evaluation_purchase_intents(
            state,
            acquisition(),
            replacement(),
            reason="growth",
        )
        self.assertEqual(len(intents), 1)
        self.assertFalse(intents[0].creates_pa_immediately)
        with self.assertRaisesRegex(ValueError, "overshoot"):
            BookPipelineState(
                target_active_pas=2,
                active_pa_ids=(1, 2),
                target_accounting="active_plus_running_and_pending",
                running_evaluation_ids=("eval-extra",),
            )

    def test_correlated_deaths_create_evaluation_not_instant_pa_intents(self) -> None:
        state = BookPipelineState(target_active_pas=3, active_pa_ids=(), target_accounting="active_plus_running_and_pending")
        intents = plan_evaluation_purchase_intents(
            state,
            acquisition(max_event=3, max_running=3),
            replacement(),
            reason="death_replacement",
            death_count=3,
        )
        self.assertEqual(len(intents), 3)
        self.assertTrue(
            all(intent.reason == "death_replacement" for intent in intents)
        )
        self.assertTrue(
            all(not intent.creates_pa_immediately for intent in intents)
        )
        never = plan_evaluation_purchase_intents(
            state,
            acquisition(max_event=3, max_running=3),
            replacement("never"),
            reason="death_replacement",
            death_count=3,
        )
        self.assertEqual(never, ())

    def test_one_death_can_request_at_most_one_replacement_evaluation(self) -> None:
        state = BookPipelineState(
            target_active_pas=3,
            active_pa_ids=(),
            target_accounting="active_plus_running_and_pending",
        )
        intents = plan_evaluation_purchase_intents(
            state,
            acquisition(max_event=3, max_running=3),
            replacement(),
            reason="death_replacement",
            death_count=1,
        )
        self.assertEqual(len(intents), 1)
        with self.assertRaisesRegex(ValueError, "death_count"):
            plan_evaluation_purchase_intents(
                state,
                acquisition(max_event=3, max_running=3),
                replacement(),
                reason="death_replacement",
            )

    def test_policy_literals_are_validated_at_runtime(self) -> None:
        with self.assertRaisesRegex(ValueError, "acquisition mode"):
            acquisition("fill_everything_typo")
        with self.assertRaisesRegex(ValueError, "target-accounting"):
            BookPipelineState(
                target_active_pas=1,
                active_pa_ids=(),
                target_accounting="implicit_default",
            )

    def test_fixed_cadence_requires_a_due_decision(self) -> None:
        state = BookPipelineState(target_active_pas=2, active_pa_ids=(), target_accounting="active_plus_running_and_pending")
        policy = acquisition(
            "fixed_cadence",
            max_event=2,
            max_running=2,
            cadence_days=30,
        )
        self.assertEqual(
            plan_evaluation_purchase_intents(
                state,
                policy,
                replacement(),
                reason="growth",
                cadence_due=False,
            ),
            (),
        )
        self.assertEqual(
            len(
                plan_evaluation_purchase_intents(
                    state,
                    policy,
                    replacement(),
                    reason="growth",
                    cadence_due=True,
                )
            ),
            1,
        )


class ExternalCapitalContractTests(unittest.TestCase):
    def test_fixed_budget_funds_exact_shortfalls_then_exhausts(self) -> None:
        policy = ExternalCapitalPolicy(
            policy_id="fixed_160",
            mode="fixed_budget",
            permitted_uses=("evaluation_purchase", "pa_activation"),
            lifetime_cap_usd=160.0,
            contribution_timing="just_in_time_exact_shortfall",
            close_event="never",
            reopens=False,
        )
        treasury = Treasury()
        first = at("2026-01-01 01:00:00")
        self.assertTrue(
            treasury.fund_and_pay_fee(
                first,
                35.0,
                "evaluation_purchase",
                "eval-1",
                policy,
            )
        )
        self.assertTrue(
            treasury.fund_and_pay_fee(
                first + timedelta(hours=1),
                125.0,
                "pa_activation",
                "pa-1",
                policy,
            )
        )
        before = tuple(treasury.ledger)
        self.assertFalse(
            treasury.fund_and_pay_fee(
                first + timedelta(hours=2),
                35.0,
                "evaluation_purchase",
                "eval-2",
                policy,
            )
        )
        self.assertEqual(tuple(treasury.ledger), before)
        self.assertEqual(treasury.external_contributions_usd, 160.0)
        self.assertEqual(treasury.cash_usd, 0.0)
        treasury.assert_integrity()

    def test_through_first_pa_bridge_closes_irreversibly(self) -> None:
        policy = ExternalCapitalPolicy(
            policy_id="through_first_pa_candidate",
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
        treasury = Treasury()
        first = at("2026-01-01 01:00:00")
        self.assertTrue(
            treasury.fund_and_pay_fee(
                first,
                35.0,
                "evaluation_purchase",
                "eval-1",
                policy,
            )
        )
        self.assertTrue(
            treasury.fund_and_pay_fee(
                first + timedelta(hours=1),
                125.0,
                "pa_activation",
                "pa-1",
                policy,
            )
        )
        treasury.observe_first_pa_activation(first + timedelta(hours=1))
        self.assertTrue(treasury.external_bridge_closed)
        self.assertFalse(
            treasury.fund_and_pay_fee(
                first + timedelta(hours=2),
                35.0,
                "evaluation_renewal",
                "eval-2",
                policy,
            )
        )
        treasury.assert_integrity()

    def test_insufficient_cap_never_contributes_a_partial_shortfall(self) -> None:
        policy = ExternalCapitalPolicy(
            policy_id="too_small",
            mode="fixed_budget",
            permitted_uses=("evaluation_purchase",),
            lifetime_cap_usd=30.0,
            contribution_timing="just_in_time_exact_shortfall",
            close_event="never",
            reopens=False,
        )
        treasury = Treasury()
        self.assertFalse(
            treasury.fund_and_pay_fee(
                at("2026-01-01 01:00:00"),
                35.0,
                "evaluation_purchase",
                "eval-1",
                policy,
            )
        )
        self.assertEqual(treasury.ledger, [])
        self.assertEqual(treasury.external_contributions_usd, 0.0)
        treasury.assert_integrity()

    def test_starting_cash_is_used_before_any_external_shortfall(self) -> None:
        policy = ExternalCapitalPolicy(
            policy_id="no_external_capital",
            mode="none",
            permitted_uses=(),
            lifetime_cap_usd=None,
            contribution_timing="just_in_time_exact_shortfall",
            close_event="never",
            reopens=False,
        )
        treasury = Treasury(starting_cash_usd=50.0)
        self.assertTrue(
            treasury.fund_and_pay_fee(
                at("2026-01-01 01:00:00"),
                35.0,
                "evaluation_purchase",
                "eval-1",
                policy,
            )
        )
        self.assertEqual(treasury.cash_usd, 15.0)
        self.assertEqual(treasury.external_contributions_usd, 0.0)
        treasury.assert_integrity()

    def test_owner_capital_and_cash_metrics_follow_distinct_identities(self) -> None:
        policy = ExternalCapitalPolicy(
            policy_id="through_first_pa",
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
        treasury = Treasury(starting_cash_usd=35.0)
        first = at("2026-01-01 01:00:00")

        # Initial owner cash buys the Evaluation; later owner capital funds the
        # PA activation. Both belong in total owner capital supplied.
        self.assertTrue(
            treasury.fund_and_pay_fee(
                first,
                35.0,
                "evaluation_purchase",
                "eval-1",
                policy,
            )
        )
        self.assertTrue(
            treasury.fund_and_pay_fee(
                first + timedelta(hours=1),
                125.0,
                "pa_activation",
                "pa-1",
                policy,
            )
        )
        treasury.observe_first_pa_activation(first + timedelta(hours=1))
        self.assertEqual(treasury.starting_cash_usd, 35.0)
        self.assertEqual(treasury.external_contributions_usd, 125.0)
        self.assertEqual(treasury.owner_capital_supplied_usd, 160.0)

        # A later fee is funded entirely from payout cash after the external
        # bridge has closed. It reduces retained cash, not recorded receipts.
        treasury.receive_payout(first + timedelta(hours=2), 500.0, "pa-1:payout-1")
        self.assertTrue(
            treasury.fund_and_pay_fee(
                first + timedelta(hours=3),
                35.0,
                "evaluation_renewal",
                "eval-2:renewal-1",
                policy,
            )
        )

        self.assertEqual(treasury.fees_paid_usd, 195.0)
        self.assertEqual(treasury.cash_usd, 465.0)
        self.assertEqual(treasury.owner_net_retained_cash_usd, 305.0)
        self.assertEqual(
            treasury.owner_net_retained_cash_usd,
            treasury.payout_receipts_usd - treasury.fees_paid_usd,
        )
        self.assertEqual(treasury.payout_receipts_net_of_owner_capital_usd, 340.0)
        self.assertNotEqual(
            treasury.owner_net_retained_cash_usd,
            treasury.payout_receipts_net_of_owner_capital_usd,
        )
        self.assertEqual(treasury.reconciliation_error_usd, 0.0)
        treasury.assert_integrity()

    def test_invalid_capital_literals_cannot_authorize_money(self) -> None:
        with self.assertRaisesRegex(ValueError, "external-capital mode"):
            ExternalCapitalPolicy(
                policy_id="invalid",
                mode="unlimited_typo",
                permitted_uses=("evaluation_purchase",),
                lifetime_cap_usd=None,
                contribution_timing="just_in_time_exact_shortfall",
                close_event="never",
                reopens=False,
            )


class RuntimeConfigTests(unittest.TestCase):
    """The config must build the primitives it names, and must gate the run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(
            (ROOT / "config" / "runtime.json").read_text(encoding="utf-8")
        )

    def test_flat_schedule_gives_every_pa_one_mnq_at_any_state(self) -> None:
        block = self.config["scaling"]
        schedule = ScalingSchedule(
            policy_id=block["selected_policy_id"],
            scope=block["scope"],
            threshold_metric=block["threshold_metric"],
            levels=tuple(
                ScalingLevel(
                    minimum_metric_usd=level["minimum_metric_usd"], mnq=level["mnq"]
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
        metrics = {1: -1_400.0, 2: 0.0, 3: 250.0, 4: 9_999_999.0}
        sizes = schedule.contracts_for_accounts(
            metrics, prior_mnq_by_pa_id={pa_id: 1 for pa_id in metrics}
        )
        self.assertEqual(set(sizes.values()), {1})

    def test_greedy_is_greedy_in_time_not_in_batch(self) -> None:
        acq = self.config["acquisition"]
        policy = AcquisitionPolicy(
            policy_id=acq["selected_policy_id"],
            mode=acq["mode"],
            max_purchases_per_decision=acq["max_purchases_per_decision"],
            max_running_evaluations=acq["maximum_running_evaluations"],
            cadence_days=acq["cadence_days"],
        )
        rep = self.config["replacement"]
        intents = plan_evaluation_purchase_intents(
            BookPipelineState(
                target_active_pas=20,
                active_pa_ids=(),
                target_accounting="active_plus_running_and_pending",
            ),
            policy,
            ReplacementPolicy(
                policy_id=rep["selected_policy_id"],
                mode=rep["mode"],
                max_purchases_per_death_event=rep["max_purchases_per_death_event"],
                shares_acquisition_pipeline=rep["shares_evaluation_pipeline"],
            ),
            reason="growth",
        )
        self.assertEqual(len(intents), 1)

    def test_capital_bridge_funds_only_its_own_chain(self) -> None:
        block = self.config["external_capital"]
        policy = ExternalCapitalPolicy(
            policy_id=block["selected_policy_id"],
            mode=block["mode"],
            permitted_uses=tuple(block["permitted_uses"]),
            lifetime_cap_usd=block["lifetime_hard_cap_usd"],
            contribution_timing=block["contribution_timing"],
            close_event=block["bridge_close_event"],
            reopens=block["bridge_reopens"],
            bridge_evaluation_id=block["bridge_chain_identity"],
        )
        self.assertTrue(
            policy.authorizes(
                "pa_activation",
                bridge_closed=False,
                contributed_usd=0.0,
                shortfall_usd=125.0,
                reference="eval-1",
            )
        )
        # A different Evaluation chain may never bridge.
        self.assertFalse(
            policy.authorizes(
                "pa_activation",
                bridge_closed=False,
                contributed_usd=0.0,
                shortfall_usd=125.0,
                reference="eval-7",
            )
        )

    def test_declared_event_order_matches_the_lifecycle_code(self) -> None:
        from milky_cow.lifecycle import _PHASE_RANK

        declared = self.config["event_order"]["order"]
        coded = [p for p, _ in sorted(_PHASE_RANK.items(), key=lambda kv: kv[1])]
        self.assertEqual(coded, declared)
        # Payout must fund the same-timestamp spends that follow it.
        for later in ("renewal", "activation", "purchase"):
            self.assertLess(declared.index("payout"), declared.index(later))


if __name__ == "__main__":
    unittest.main()
