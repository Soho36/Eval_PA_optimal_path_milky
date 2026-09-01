from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import unittest

from eval_pa_optimal_path.evaluation import simulate_evaluation
from eval_pa_optimal_path.io import (
    global_one_position_counts,
    load_rr1_offers,
    positive_duration_peak_overlap,
)
from eval_pa_optimal_path.rules import Legacy25KRules
from eval_pa_optimal_path.timezones import get_timezone


ROOT = Path(__file__).resolve().parents[1]


class RawTapeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.offers = load_rr1_offers(ROOT / "data/raw/rr1")

    def test_audited_counts_and_capacity(self):
        self.assertEqual(len(self.offers), 12_658)
        self.assertEqual(global_one_position_counts(self.offers), (9_299, 3_359))
        self.assertEqual(positive_duration_peak_overlap(self.offers), 5)
        self.assertEqual(
            sum(offer.entry_at == offer.exit_at for offer in self.offers), 1
        )
        self.assertEqual(
            len({offer.entry_at for offer in self.offers}), len(self.offers)
        )

    def test_tallinn_dst_is_attached(self):
        self.assertEqual(self.offers[0].entry_at.utcoffset(), timedelta(hours=2))
        summer = next(offer for offer in self.offers if offer.entry_at.month == 7)
        self.assertEqual(summer.entry_at.utcoffset(), timedelta(hours=3))


class EodmaeEvaluationParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.offers = load_rr1_offers(ROOT / "data/raw/rr1")
        cls.zone = get_timezone("Europe/Tallinn")
        cls.rules = replace(
            Legacy25KRules(), evaluation_minimum_trading_days=1
        )

    def run_case(self, start_label: str):
        start = datetime.strptime(start_label, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=self.zone
        )
        return simulate_evaluation(
            self.offers, start, start + timedelta(days=180), self.rules
        )

    def test_representative_pass_after_live_renewal(self):
        result = self.run_case("2020-01-02 01:00:00")
        self.assertEqual(result.status, "passed")
        self.assertEqual(
            result.pass_at.replace(tzinfo=None), datetime(2020, 2, 6, 6, 30)
        )
        self.assertEqual(result.evaluation_fees_usd, 70)
        self.assertEqual((result.trades, result.blocked_offers), (144, 46))
        self.assertEqual((result.failures_dd, result.carried_renewals), (0, 1))

    def test_representative_failures_then_pass(self):
        result = self.run_case("2020-01-03 01:00:00")
        self.assertEqual(result.status, "passed")
        self.assertEqual(
            result.pass_at.replace(tzinfo=None), datetime(2020, 4, 7, 11, 30)
        )
        self.assertEqual(result.evaluation_fees_usd, 140)
        self.assertEqual((result.trades, result.blocked_offers), (241, 84))
        self.assertEqual((result.failures_dd, result.carried_renewals), (2, 1))

    def test_representative_censored_episode(self):
        result = self.run_case("2020-01-06 01:00:00")
        self.assertEqual(result.status, "censored")
        self.assertIsNone(result.pass_at)
        self.assertEqual(result.evaluation_fees_usd, 210)
        self.assertEqual((result.trades, result.blocked_offers), (300, 100))
        self.assertEqual((result.failures_dd, result.carried_renewals), (5, 1))


if __name__ == "__main__":
    unittest.main()

