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
        self.assertIsNone(gate["opportunity_stream"]["evaluation_consumer_mode"])
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


if __name__ == "__main__":
    unittest.main()
