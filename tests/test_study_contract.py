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
        self.assertEqual(
            gate["pa_book"]["distribution"],
            "copy_to_all_eligible_active_pas",
        )
        unresolved = set(gate["unresolved_before_integrated_sweep"])
        self.assertIn("evaluation_consumer_mode", unresolved)
        self.assertIn("scaling_policy_and_thresholds", unresolved)
        self.assertIn("replacement_policy", unresolved)
        self.assertIn("external_capital_policy_and_budget", unresolved)
        self.assertIn("economic_objective", unresolved)


if __name__ == "__main__":
    unittest.main()
