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
from milky_cow.inputs import PATH_COIN_SEED, get_timezone
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


class IntegratedSweepGateTests(unittest.TestCase):
    def test_contract_gate_covers_every_pa_count_and_remains_closed(self) -> None:
        gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            gate["pa_book"]["active_pa_count_values"],
            list(range(1, 21)),
        )
        self.assertEqual(
            gate["pa_book"]["distribution"],
            "copy_to_all_eligible_active_pas",
        )
        self.assertEqual(
            gate["opportunity_stream"]["evaluation_consumer_mode"],
            "cycle_local_one_position_restarted_at_each_renewal_boundary",
        )
        self.assertGreater(
            len(gate["unresolved_before_integrated_sweep"]),
            0,
        )
        self.assertNotIn("router", gate["pa_book"])
        self.assertEqual(
            set(gate["pa_book"]["allowed_roles"]),
            {"active_alive", "dead"},
        )
        axis = gate["pa_book"]["active_pa_count_axis_semantics"]
        self.assertEqual(
            axis["headline_estimand"],
            "maintained_target_active_pas_acquired_from_zero",
        )
        self.assertEqual(axis["initial_state"], "zero_evaluations_zero_pas")
        self.assertIn("active_plus_running_evaluations_plus_pending_activations", axis["hard_cap_accounting"])
        self.assertNotIn(
            "active_pa_count_axis_semantics",
            gate["unresolved_before_integrated_sweep"],
        )

        path = gate["intratrade_path_order"]
        self.assertEqual(
            path["scenario_arms"],
            [
                "source_constrained_then_mae_first",
                "source_constrained_then_mfe_first",
                "source_constrained_then_seeded_coin",
            ],
        )
        self.assertEqual(path["phase_scope"], ["evaluation", "pa"])
        self.assertEqual(path["rr1_source_population_evidence"]["accepted_ambiguous_opportunities"], 3_722)
        self.assertEqual(
            path["delta_reference"],
            "source_constrained_then_seeded_coin",
        )
        self.assertEqual(path["resolver_seed"], PATH_COIN_SEED)
        acquisition = gate["acquisition"]
        self.assertIn("running_evaluation", acquisition["pipeline_credit_toward_target"])
        self.assertIn("exceed_n", acquisition["overshoot_behavior"])

    def test_active_gate_hash_binds_its_evidence_and_supersedes_initial_scope(self) -> None:
        gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(
            gate["governance"]["runtime_merge_with_parent_or_initial_contract"]
        )
        self.assertEqual(
            gate["governance"]["superseded_artifact_role"],
            "frozen_transfer_evidence_only",
        )
        for row in gate["evidence_bindings"]:
            digest = hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
            self.assertEqual(digest, row["sha256"], row["path"])

    def test_exact_six_payout_candidates_match_the_candidate_file(self) -> None:
        gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text(
                encoding="utf-8"
            )
        )
        policies = json.loads(
            (ROOT / "config" / "payout_policies.json").read_text(
                encoding="utf-8"
            )
        )
        expected = {row["policy_id"] for row in policies["policies"]}
        self.assertEqual(
            set(gate["payout_candidates"]["policy_ids"]),
            expected,
        )
        self.assertEqual(len(expected), 6)


class ResolvedParentParityPolicyTests(unittest.TestCase):
    """The seven fields resolved for parity with the parent must be buildable.

    A gate value that cannot construct the primitive it names is prose, not a
    contract, so every resolved policy is instantiated from the gate itself.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text(
                encoding="utf-8"
            )
        )

    def test_flat_schedule_gives_every_pa_one_mnq_at_any_state(self) -> None:
        block = self.gate["scaling"]
        self.assertEqual(block["selected_policy_id"], "flat_one_mnq_no_scaling_phase_1")
        self.assertEqual(block["commission_timing"], "close_only")
        self.assertEqual(block["maximum_mnq"], 1)
        schedule = ScalingSchedule(
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
        metrics = {1: -1_400.0, 2: 0.0, 3: 250.0, 4: 9_999_999.0}
        sizes = schedule.contracts_for_accounts(
            metrics, prior_mnq_by_pa_id={pa_id: 1 for pa_id in metrics}
        )
        self.assertEqual(set(sizes.values()), {1})

    def test_acquisition_and_replacement_build_the_parent_baseline_arm(self) -> None:
        acq = self.gate["acquisition"]
        rep = self.gate["replacement"]
        self.assertEqual(acq["selected_policy_id"], "greedy_to_target_parent_baseline")
        policy = AcquisitionPolicy(
            policy_id=acq["selected_policy_id"],
            mode=acq["mode"],
            max_purchases_per_decision=acq["max_purchases_per_decision"],
            max_running_evaluations=acq["maximum_running_evaluations"],
            cadence_days=acq["cadence_days"],
        )
        self.assertEqual(policy.mode, "one_per_decision")
        self.assertIsNone(policy.cadence_days)
        replacement = ReplacementPolicy(
            policy_id=rep["selected_policy_id"],
            mode=rep["mode"],
            max_purchases_per_death_event=rep["max_purchases_per_death_event"],
            shares_acquisition_pipeline=rep["shares_evaluation_pipeline"],
        )
        self.assertTrue(replacement.shares_acquisition_pipeline)
        # Greedy is greedy in time, not in batch: an empty book at N=20 still
        # buys exactly one Evaluation per decision.
        intents = plan_evaluation_purchase_intents(
            BookPipelineState(
                target_active_pas=20,
                active_pa_ids=(),
                target_accounting=acq["executable_target_accounting_contracts"][0],
            ),
            policy,
            replacement,
            reason="growth",
        )
        self.assertEqual(len(intents), 1)

    def test_capital_bridge_funds_before_first_pa_and_never_after(self) -> None:
        block = self.gate["external_capital"]
        self.assertEqual(block["starting_cash_usd"], 35.0)
        self.assertIsNone(block["lifetime_hard_cap_usd"])
        policy = ExternalCapitalPolicy(
            policy_id=block["selected_policy_id"],
            mode=block["mode"],
            permitted_uses=tuple(block["permitted_uses"]),
            lifetime_cap_usd=block["lifetime_hard_cap_usd"],
            contribution_timing=block["contribution_timing"],
            close_event=block["bridge_close_event"],
            reopens=block["bridge_reopens"],
        )
        self.assertFalse(policy.reopens)
        for purpose in ("evaluation_purchase", "evaluation_renewal", "pa_activation"):
            self.assertTrue(
                policy.authorizes(
                    purpose,
                    bridge_closed=False,
                    contributed_usd=0.0,
                    shortfall_usd=125.0,
                )
            )
            self.assertFalse(
                policy.authorizes(
                    purpose,
                    bridge_closed=True,
                    contributed_usd=160.0,
                    shortfall_usd=125.0,
                )
            )

    def test_parent_comparison_pins_the_revision_and_the_delta_arm(self) -> None:
        parent = self.gate["parent_comparison"]
        self.assertEqual(
            parent["parent_revision"],
            "106cfb782c6e573856282095441bb69f23924a55",
        )
        # The parent pinned mae_first; differencing against the seeded coin
        # would compare two different path-order treatments.
        self.assertEqual(
            parent["comparison_arm_for_parent_delta"],
            "source_constrained_then_mae_first",
        )
        self.assertIn(
            parent["comparison_arm_for_parent_delta"],
            self.gate["intratrade_path_order"]["scenario_arms"],
        )
        self.assertNotEqual(
            parent["comparison_arm_for_parent_delta"],
            self.gate["intratrade_path_order"]["delta_reference"],
        )
        # K=5 is a parent selection and must never become this study's axis.
        self.assertIn("target_pa_count_k", parent["not_adopted"])
        self.assertEqual(
            self.gate["pa_book"]["active_pa_count_values"], list(range(1, 21))
        )

    def test_unmodelled_execution_records_its_bias_direction(self) -> None:
        stress = self.gate["reporting"]["stress_scenarios"][
            "aggregate_execution_and_slippage"
        ]
        self.assertFalse(stress["modeled"])
        self.assertEqual(stress["known_bias_direction"], "favors_high_n")

    def test_evaluation_consumer_resets_per_cycle_unlike_the_pa_stream(self) -> None:
        stream = self.gate["opportunity_stream"]
        self.assertEqual(
            stream["evaluation_consumer_mode"],
            "cycle_local_one_position_restarted_at_each_renewal_boundary",
        )
        contract = stream["evaluation_consumer_contract"]
        self.assertEqual(contract["selector_reset_scope"], "every_renewal_boundary")
        self.assertEqual(stream["selector_reset_scope"], "never_for_pa_book_scenarios")
        # The Evaluation runs 3 MNQ; phase-1 "no scaling" is a PA-only decision.
        self.assertEqual(contract["position_size_mnq"], 3)
        self.assertEqual(self.gate["scaling"]["maximum_mnq"], 1)


if __name__ == "__main__":
    unittest.main()
