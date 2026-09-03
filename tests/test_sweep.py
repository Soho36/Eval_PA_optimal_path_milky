from __future__ import annotations

from pathlib import Path
import unittest

from milky_cow.cohorts import first_session_monthly_cohorts
from milky_cow.inputs import load_verified_rr1_dataset
from milky_cow.sweep import build_grid, run_arm, summarize_arm


ROOT = Path(__file__).resolve().parents[1]


class GridTests(unittest.TestCase):
    def test_grid_is_the_full_product_in_a_stable_order(self) -> None:
        grid = build_grid(
            [1, 2],
            ["minimum_500_always", "maximum_always"],
            path_stress_arm="source_constrained_then_seeded_coin",
            event_order_mode="canonical_settle_realize_spend_commit",
        )
        self.assertEqual(len(grid), 4)
        # The grid follows the caller's order — which is the gate's declared
        # policy order — rather than re-sorting it, and repeats exactly.
        self.assertEqual(
            [(row[0], row[1]) for row in grid],
            [
                (1, "minimum_500_always"),
                (1, "maximum_always"),
                (2, "minimum_500_always"),
                (2, "maximum_always"),
            ],
        )
        # Every arm carries its own path and ordering, so a sweep can never
        # mix two treatments in one manifest by accident.
        self.assertEqual({row[2] for row in grid}, {"source_constrained_then_seeded_coin"})
        self.assertEqual({row[3] for row in grid}, {"canonical_settle_realize_spend_commit"})


class ArmSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_verified_rr1_dataset(ROOT / "data" / "raw" / "rr1")
        cls.cohorts = first_session_monthly_cohorts(
            cls.dataset.selection.accepted_opportunities, horizon_days=720
        ).cohorts[:6]

    def test_arm_aggregates_every_cohort_and_stays_deterministic(self) -> None:
        first, results = run_arm(
            ROOT,
            self.dataset,
            self.cohorts,
            target_active_pas=2,
            payout_policy_id="minimum_500_always",
            exploratory=True,
        )
        second, _ = run_arm(
            ROOT,
            self.dataset,
            self.cohorts,
            target_active_pas=2,
            payout_policy_id="minimum_500_always",
            exploratory=True,
        )
        self.assertEqual(first.as_row(), second.as_row())
        self.assertEqual(first.cohort_count, len(self.cohorts))
        self.assertEqual(len(results), len(self.cohorts))

    def test_summary_totals_match_the_underlying_cohorts(self) -> None:
        summary, results = run_arm(
            ROOT,
            self.dataset,
            self.cohorts,
            target_active_pas=2,
            payout_policy_id="minimum_500_always",
            exploratory=True,
        )
        self.assertEqual(
            summary.pas_activated, sum(row.pas_activated for row in results)
        )
        self.assertEqual(summary.pa_deaths, sum(row.pa_deaths for row in results))
        self.assertEqual(
            summary.payouts_executed, sum(row.payouts_executed for row in results)
        )
        self.assertEqual(
            summary.retained_min_usd,
            min(row.owner_net_retained_cash_usd for row in results),
        )
        self.assertEqual(
            summary.retained_max_usd,
            max(row.owner_net_retained_cash_usd for row in results),
        )

    def test_quantiles_are_ordered(self) -> None:
        summary, _ = run_arm(
            ROOT,
            self.dataset,
            self.cohorts,
            target_active_pas=1,
            payout_policy_id="minimum_500_always",
            exploratory=True,
        )
        self.assertLessEqual(summary.retained_min_usd, summary.retained_p25_usd)
        self.assertLessEqual(summary.retained_p25_usd, summary.retained_median_usd)
        self.assertLessEqual(summary.retained_median_usd, summary.retained_p75_usd)
        self.assertLessEqual(summary.retained_p75_usd, summary.retained_max_usd)

    def test_unwithdrawn_equity_is_never_folded_into_the_headline(self) -> None:
        summary, _ = run_arm(
            ROOT,
            self.dataset,
            self.cohorts,
            target_active_pas=2,
            payout_policy_id="maximum_always",
            exploratory=True,
        )
        row = summary.as_row()
        self.assertNotIn(
            "unwithdrawn_equity_total_usd", row["owner_net_retained_cash_usd"]
        )
        self.assertIn("unwithdrawn_equity_total_usd", row["right_censoring"])

    def test_summarize_rejects_an_empty_arm(self) -> None:
        with self.assertRaises(ValueError):
            summarize_arm([])


if __name__ == "__main__":
    unittest.main()
