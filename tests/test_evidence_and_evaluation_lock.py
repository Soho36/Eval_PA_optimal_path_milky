from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest

from milky_cow.evaluation_lock import simulate_eodmae_evaluation_lock
from milky_cow.inputs import (
    get_timezone,
    load_rr1_offers,
    select_global_one_position,
    verify_rr1_import,
)
from milky_cow.provenance import (
    verify_implementation_provenance,
    verify_transfer_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


class EvidenceAndEvaluationLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw_root = ROOT / "data" / "raw" / "rr1"
        cls.offers = load_rr1_offers(cls.raw_root)
        cls.selection = select_global_one_position(cls.offers)
        cls.zone = get_timezone("Europe/Tallinn")
        cls.fixture = json.loads(
            (
                ROOT
                / "tests"
                / "fixtures"
                / "evaluation"
                / "eodmae_legacy_25k_x3_behavior_lock.json"
            ).read_text(encoding="utf-8")
        )

    def test_transfer_receipt_preserves_every_imported_parent_artifact(self) -> None:
        result = verify_transfer_snapshot(ROOT)
        self.assertEqual(result.manifest_entries, 96)
        self.assertEqual(result.parent_snapshot_entries, 73)
        self.assertEqual(result.parent_snapshot_exact, 73)
        self.assertEqual(result.initial_exact_entries, 94)
        self.assertEqual(result.exact_entries, 83)
        self.assertEqual(result.project_developed_entries, 11)
        self.assertEqual(result.acknowledged_deviations, 2)

    def test_implementation_derivatives_are_hash_bound_to_reviewed_sources(self) -> None:
        result = verify_implementation_provenance(ROOT)
        self.assertEqual(result.reviewed_sources, 7)
        self.assertGreaterEqual(result.local_artifacts, 19)
        self.assertEqual(result.derivations, 5)

    def test_rr1_manifest_and_global_stream_parity(self) -> None:
        verified = verify_rr1_import(self.raw_root)
        self.assertEqual((verified.files, verified.bytes), (46, 1_725_388))
        self.assertEqual(
            verified.combined_set_sha256,
            "1bf2f1c83fe96bf5b86653583f33f52c35631cf0ea561566e0dcb35756274f7e",
        )
        self.assertEqual(len(self.offers), 12_658)
        self.assertEqual(len(self.selection.accepted), 9_299)
        self.assertEqual(len(self.selection.blocked), 3_359)
        self.assertEqual(
            self.selection.accepted_stream_sha256,
            "1175787ba50f0ab9f08a953f60b661e597c70f2bdb9329a517603616aaae6759",
        )
        accepted_records = self.selection.accepted_opportunities
        self.assertEqual(len(accepted_records), 9_299)
        self.assertEqual(accepted_records[0].accepted_ordinal, 1)
        self.assertEqual(accepted_records[-1].accepted_ordinal, 9_299)
        self.assertEqual(
            accepted_records[0].accepted_stream_sha256,
            self.selection.accepted_stream_sha256,
        )
        self.assertEqual(
            sum(offer.entry_at == offer.exit_at for offer in self.offers),
            1,
        )
        self.assertEqual(
            len({offer.entry_at for offer in self.offers}),
            len(self.offers),
        )
        self.assertTrue(
            all(
                left.exit_at <= right.entry_at
                for left, right in zip(
                    self.selection.accepted,
                    self.selection.accepted[1:],
                )
            )
        )

    def test_tallinn_dst_is_attached(self) -> None:
        winter = self.offers[0]
        summer = next(
            offer for offer in self.offers if offer.entry_at.month == 7
        )
        self.assertEqual(winter.entry_at.utcoffset(), timedelta(hours=2))
        self.assertEqual(summer.entry_at.utcoffset(), timedelta(hours=3))

    def test_three_pinned_eodmae_episodes_are_executable_behavior_locks(self) -> None:
        for expected in self.fixture["representative_episodes"]:
            with self.subTest(start=expected["start_time"]):
                start = datetime.strptime(
                    expected["start_time"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=self.zone)
                result = simulate_eodmae_evaluation_lock(
                    self.offers,
                    start,
                    start + timedelta(days=180),
                )
                expected_status = (
                    "passed"
                    if expected["status"] == "activated"
                    else expected["status"]
                )
                self.assertEqual(result.status, expected_status)
                expected_pass = expected["activation_time"]
                if expected_pass is None:
                    self.assertIsNone(result.pass_at)
                else:
                    self.assertEqual(
                        result.pass_at.replace(tzinfo=None),
                        datetime.strptime(expected_pass, "%Y-%m-%d %H:%M:%S"),
                    )
                self.assertEqual(
                    result.evaluation_fees_usd,
                    float(expected["evaluation_fees_paid"]),
                )
                self.assertEqual(result.attempts, expected["attempts"])
                self.assertEqual(result.trades, expected["trades"])
                self.assertEqual(
                    result.blocked_offers,
                    expected["blocked_offers"],
                )
                self.assertEqual(result.failures_dd, expected["failures_dd"])
                self.assertEqual(
                    result.carried_renewals,
                    expected["carried_renewals"],
                )


if __name__ == "__main__":
    unittest.main()
