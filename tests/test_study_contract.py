import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StudyContractTests(unittest.TestCase):
    def test_initial_scope_record_is_preserved_but_superseded_for_runtime(self) -> None:
        initial = json.loads(
            (ROOT / "config" / "milky_cow_study_contract.json").read_text(
                encoding="utf-8"
            )
        )
        gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            initial["pa_book"]["signal_distribution"],
            "copy_to_all_eligible_active_pas",
        )
        self.assertEqual(
            gate["governance"]["superseded_initial_scope_record"],
            "config/milky_cow_study_contract.json",
        )
        self.assertFalse(
            gate["governance"]["runtime_merge_with_parent_or_initial_contract"]
        )

    def test_active_gate_has_full_count_axis_and_remains_closed(self) -> None:
        gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            gate["pa_book"]["active_pa_count_values"],
            list(range(1, 21)),
        )
        self.assertEqual(gate["schema_version"], "milky_cow_contract_gate.v5")
        self.assertEqual(
            gate["pa_book"]["distribution"],
            "copy_to_all_eligible_active_pas",
        )
        self.assertEqual(
            gate["unresolved_before_integrated_sweep"],
            [],
        )
        self.assertEqual(
            gate["status"],
            "exploratory_v0_produced_defects_found_reruns_required",
        )
        self.assertTrue(gate["remaining_blockers_before_the_sweep"])
        self.assertEqual(
            {
                row["id"]: row["selected"]
                for row in gate["resolved_user_decisions_2026_09_02"]
            },
            {
                "external_capital_bridge_scope": "first_pa_chain_only",
                "headline_economic_objective": "owner_net_retained_cash",
                "event_order_sensitivity_permutation": "spend_before_payout",
                "horizon_crossing_trade_treatment": (
                    "admit_before_horizon_leave_open_trade_unscored"
                ),
            },
        )
        fixture = gate["deterministic_vertical_slice_fixture"]
        self.assertEqual(
            fixture["status"],
            "executable_contract_fixture_not_study_baseline",
        )
        self.assertEqual(fixture["pa_targets"], [1, 2])
        self.assertEqual(
            fixture["evaluation_consumer_boundary"],
            "adapter_invariant_nonoverlapping_synthetic_offers",
        )
        self.assertEqual(
            fixture["pa_stream_binding"],
            "exact_opportunity_selection_digest_raw_count_ordinal_and_offer",
        )
        self.assertEqual(
            gate["opportunity_stream"]["expected_zero_duration_offers"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
