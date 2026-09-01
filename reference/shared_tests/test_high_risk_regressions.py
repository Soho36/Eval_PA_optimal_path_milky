from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import unittest

from eval_pa_optimal_path.io import verify_rr1_import
from eval_pa_optimal_path.models import CashLedgerEntry
from eval_pa_optimal_path.pa import PAState
from eval_pa_optimal_path.payouts import execute_payout, maximum_eligible_gross
from eval_pa_optimal_path.rules import Legacy25KRules, PayoutPolicy, StudyConfig
from eval_pa_optimal_path.simulation import simulate_cohort
from eval_pa_optimal_path.timezones import localize_wall_time
from eval_pa_optimal_path.treasury import Treasury

from _helpers import at, offer


ROOT = Path(__file__).resolve().parents[1]
MINIMUM_POLICY = PayoutPolicy.of("minimum", "minimum")


class LedgerIntegrityTests(unittest.TestCase):
    def test_row_level_balance_tamper_is_rejected(self):
        treasury = Treasury()
        event_at = at("2023-01-01 01:00:00")
        treasury.contribute(event_at, 35, "seed")
        self.assertTrue(
            treasury.spend_fee(event_at, 35, "evaluation_fee", "evaluation:1")
        )
        treasury.assert_ledger_integrity()

        row = treasury.ledger[-1]
        treasury.ledger[-1] = CashLedgerEntry(
            row.event_at,
            row.kind,
            row.amount_usd,
            row.reference,
            1.0,
        )
        with self.assertRaisesRegex(RuntimeError, "row 2 balance mismatch"):
            treasury.assert_ledger_integrity()


class SameTimestampLifecycleTests(unittest.TestCase):
    def test_payout_cash_renews_existing_evaluation_before_new_purchase(self):
        offers = [
            offer(
                "bootstrap-pass",
                "2023-01-01 01:00:00",
                "2023-01-01 02:00:00",
                1000,
            ),
            offer(
                "first-payout",
                "2023-01-02 01:00:00",
                "2023-01-02 02:00:00",
                1600,
            ),
            offer(
                "renewal-day-payout",
                "2023-01-03 01:00:00",
                "2023-01-03 02:00:00",
                500,
            ),
            offer(
                "post-renewal-pass",
                "2023-01-04 01:00:00",
                "2023-01-04 02:00:00",
                500,
            ),
        ]
        rules = replace(
            Legacy25KRules(),
            evaluation_profit_target_usd=3000,
            evaluation_trailing_drawdown_usd=5000,
            evaluation_fee_usd=500,
            evaluation_cycle_days=1,
            payout_minimum_days=1,
            payout_minimum_profitable_days=1,
        )
        study = replace(StudyConfig(), target_pa_count_k=3)

        result = simulate_cohort(
            offers,
            at("2023-01-01 01:00:00"),
            at("2023-01-04 03:00:00"),
            rules,
            study,
            MINIMUM_POLICY,
        )

        renewal_at = at("2023-01-03 23:59:00")
        same_time = [entry for entry in result.ledger if entry.event_at == renewal_at]
        self.assertEqual(
            [(entry.kind, entry.amount_usd) for entry in same_time],
            [("payout", 500), ("evaluation_fee", -500)],
        )
        self.assertIn("renewal:2", same_time[1].reference)
        self.assertFalse(
            any(entry.reference == "evaluation:3:purchase" for entry in result.ledger)
        )
        self.assertEqual(result.evaluation_purchases, 2)
        self.assertEqual(result.evaluation_passes, 2)
        self.assertEqual(result.gross_payouts_usd, 1000)
        self.assertEqual(result.cash_reconciliation_error_usd, 0)

    def test_signal_at_activation_is_requested_but_unfilled(self):
        offers = [
            offer(
                "evaluation-pass",
                "2023-01-01 01:00:00",
                "2023-01-01 02:00:00",
                100,
            ),
            offer(
                "activation-tie",
                "2023-01-01 02:00:00",
                "2023-01-01 03:00:00",
                10,
            ),
        ]
        rules = replace(Legacy25KRules(), evaluation_profit_target_usd=300)
        study = replace(StudyConfig(), target_pa_count_k=1)

        result = simulate_cohort(
            offers,
            at("2023-01-01 01:00:00"),
            at("2023-01-02 01:00:00"),
            rules,
            study,
            MINIMUM_POLICY,
        )

        self.assertEqual(result.first_pa_at, at("2023-01-01 02:00:00"))
        self.assertEqual(result.requested_copies, 1)
        self.assertEqual(result.filled_copies, 0)
        self.assertEqual(len(result.routing_decisions), 1)
        decision = result.routing_decisions[0]
        self.assertEqual(decision.signal_key, "activation-tie")
        self.assertEqual(decision.requested_copies, 1)
        self.assertEqual(decision.filled_copies, 0)
        self.assertEqual(decision.rejection_reason, "no_tradable_pa")


class PayoutBoundaryTests(unittest.TestCase):
    def make_pa(self, payout_count: int, balance_usd: float) -> PAState:
        rules = Legacy25KRules()
        pa = PAState.create(1, at("2023-01-01 00:00:00"), rules)
        pa.payout_count = payout_count
        pa.equity_profit_usd = balance_usd - rules.nominal_balance_usd
        return pa

    def test_third_to_fourth_payout_switch_and_one_cent_floor(self):
        rules = Legacy25KRules()

        third = self.make_pa(payout_count=2, balance_usd=27_000)
        fourth = self.make_pa(payout_count=3, balance_usd=27_000)
        self.assertEqual(maximum_eligible_gross(third, rules), 900)
        self.assertEqual(maximum_eligible_gross(fourth, rules), 1500)

        fourth_at_gate = self.make_pa(payout_count=3, balance_usd=26_600)
        self.assertEqual(maximum_eligible_gross(fourth_at_gate, rules), 1499.99)
        record = execute_payout(
            fourth_at_gate,
            at("2023-01-09 23:59:00"),
            1499.99,
            rules,
            PayoutPolicy.of("maximum", "maximum"),
        )
        self.assertEqual(record.payout_number, 4)
        self.assertEqual(record.balance_after_usd, 25_100.01)

    def test_fifth_to_sixth_payout_removes_fixed_cap(self):
        rules = Legacy25KRules()
        fifth = self.make_pa(payout_count=4, balance_usd=28_000)
        sixth = self.make_pa(payout_count=5, balance_usd=28_000)

        self.assertEqual(maximum_eligible_gross(fifth, rules), 1500)
        self.assertEqual(maximum_eligible_gross(sixth, rules), 2899.99)


class TimezoneAndManifestIntegrityTests(unittest.TestCase):
    def test_tallinn_nonexistent_spring_wall_time_is_rejected(self):
        nonexistent = datetime(2026, 3, 29, 3, 30)
        with self.assertRaisesRegex(ValueError, "Nonexistent Europe/Tallinn"):
            localize_wall_time(nonexistent, "Europe/Tallinn")

    def test_raw_manifest_rejects_extra_and_same_size_tamper(self):
        source = ROOT / "data" / "raw" / "rr1"
        manifest = ROOT / "manifests" / "rr1_import_20260829.json"
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "rr1"
            shutil.copytree(source, copied)

            extra = copied / "unexpected.txt"
            extra.write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "file set mismatch"):
                verify_rr1_import(copied, manifest)
            extra.unlink()

            target = next(path for path in sorted(copied.rglob("*")) if path.is_file())
            original = bytearray(target.read_bytes())
            original[-1] ^= 1
            target.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_rr1_import(copied, manifest)


if __name__ == "__main__":
    unittest.main()
