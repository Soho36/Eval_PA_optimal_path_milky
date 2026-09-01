import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StudyContractTests(unittest.TestCase):
    def test_copy_to_all_scope_is_locked(self) -> None:
        contract = json.loads(
            (ROOT / "config" / "milky_cow_study_contract.json").read_text(
                encoding="utf-8"
            )
        )
        book = contract["pa_book"]
        self.assertEqual(
            book["signal_distribution"], "copy_to_all_eligible_active_pas"
        )
        self.assertFalse(book["staggering"])
        self.assertFalse(book["routing_competition"])
        self.assertFalse(book["dormant_pa_reserve"])
        self.assertEqual(max(book["candidate_active_pa_counts"]), 20)

    def test_sweep_blockers_remain_explicit(self) -> None:
        contract = json.loads(
            (ROOT / "config" / "milky_cow_study_contract.json").read_text(
                encoding="utf-8"
            )
        )
        unresolved = set(contract["unresolved_before_integrated_sweep"])
        self.assertIn("contract_scaling_schedule", unresolved)
        self.assertIn("dead_pa_replacement_policy", unresolved)
        self.assertIn("external_capital_budget", unresolved)


if __name__ == "__main__":
    unittest.main()
