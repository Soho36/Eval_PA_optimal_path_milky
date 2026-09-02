from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import unittest

from milky_cow.cohorts import first_session_monthly_cohorts
from milky_cow.evaluation_lock import simulate_eodmae_evaluation_lock
from milky_cow.inputs import (
    get_timezone,
    localize_wall_time,
    load_verified_rr1_dataset,
    path_order_for_offer,
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
        cls.dataset = load_verified_rr1_dataset(cls.raw_root)
        cls.offers = cls.dataset.offers
        cls.selection = cls.dataset.selection
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
        self.assertEqual(result.initial_exact_entries, 95)
        self.assertEqual(result.exact_entries, 83)
        self.assertEqual(result.project_developed_entries, 12)
        self.assertEqual(result.acknowledged_deviations, 1)

    def test_implementation_derivatives_are_hash_bound_to_reviewed_sources(self) -> None:
        result = verify_implementation_provenance(ROOT)
        self.assertEqual(result.reviewed_sources, 8)
        self.assertGreaterEqual(result.local_artifacts, 23)
        self.assertEqual(result.derivations, 7)

    def test_rr1_manifest_and_global_stream_parity(self) -> None:
        verified = self.dataset.verification
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
        ambiguous = [
            record
            for record in accepted_records
            if record.offer.intratrade_path_status == "ambiguous"
        ]
        self.assertEqual(
            (
                sum(
                    offer.intratrade_path_status == "ambiguous"
                    for offer in self.offers
                ),
                len(ambiguous),
                sum(
                    offer.intratrade_path_status == "ambiguous"
                    for offer in self.selection.blocked
                ),
            ),
            (5_029, 3_722, 1_307),
        )
        central_arm = "source_constrained_then_seeded_coin"
        assignments = [
            (record, path_order_for_offer(record.offer, central_arm))
            for record in ambiguous
        ]
        self.assertEqual(
            (
                sum(order == "mae_first" for _, order in assignments),
                sum(order == "mfe_first" for _, order in assignments),
            ),
            (1_838, 1_884),
        )
        assignment_digest = hashlib.sha256()
        for record, order in assignments:
            assignment_digest.update(record.offer.trade_key.encode("utf-8"))
            assignment_digest.update(b"\0")
            assignment_digest.update(order.encode("utf-8"))
            assignment_digest.update(b"\n")
        self.assertEqual(
            assignment_digest.hexdigest(),
            "fe8ffebb92966bfb40675100b7a56d5977c0cc1c40bfbe9d4e3aea2341bdda45",
        )
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
        with self.assertRaisesRegex(ValueError, "Nonexistent"):
            localize_wall_time(
                datetime(2024, 3, 31, 3, 30),
                "Europe/Tallinn",
            )
        repeated = datetime(2024, 10, 27, 3, 30)
        fold_zero = localize_wall_time(repeated, "Europe/Tallinn", fold=0)
        fold_one = localize_wall_time(repeated, "Europe/Tallinn", fold=1)
        self.assertEqual(fold_zero.utcoffset(), timedelta(hours=3))
        self.assertEqual(fold_one.utcoffset(), timedelta(hours=2))

    def test_accepted_stream_evidence_records_are_cached_once(self) -> None:
        first_digest = self.selection.accepted_stream_sha256
        first_records = self.selection.accepted_opportunities
        self.assertIs(self.selection.accepted_stream_sha256, first_digest)
        self.assertIs(self.selection.accepted_opportunities, first_records)
        self.assertEqual(
            first_digest,
            "1175787ba50f0ab9f08a953f60b661e597c70f2bdb9329a517603616aaae6759",
        )
        self.assertEqual(len(first_records), 9_299)

    def test_monthly_cohorts_distinguish_complete_from_censored_horizons(self) -> None:
        accepted = self.selection.accepted_opportunities
        complete = first_session_monthly_cohorts(
            accepted,
            horizon_days=720,
            require_full_horizon=True,
        )
        all_starts = first_session_monthly_cohorts(
            accepted,
            horizon_days=720,
            require_full_horizon=False,
        )

        self.assertEqual(
            (
                complete.all_count,
                complete.fully_observed_count,
                complete.tape_censored_count,
                len(complete.cohorts),
                len(all_starts.cohorts),
            ),
            (79, 55, 24, 55, 79),
        )
        self.assertEqual(complete.all_cohorts, all_starts.all_cohorts)
        self.assertEqual(
            complete.tape_observation_end_at.isoformat(),
            "2026-07-13T21:30:40+03:00",
        )
        self.assertEqual(
            complete.cohorts[-1].start_at.isoformat(),
            "2024-07-01T01:00:00+03:00",
        )
        self.assertEqual(
            complete.all_cohorts[55].start_at.isoformat(),
            "2024-08-01T01:00:00+03:00",
        )
        self.assertTrue(
            all(
                cohort.start_at.tzinfo is not None
                and cohort.horizon_end_at.tzinfo is not None
                and cohort.horizon_end_at == cohort.start_at + timedelta(days=720)
                for cohort in complete.all_cohorts
            )
        )
        self.assertEqual(
            complete.all_cohorts[0].start_at.isoformat(),
            "2020-01-02T01:00:00+02:00",
        )
        self.assertEqual(
            complete.all_cohorts[-1].start_at.isoformat(),
            "2026-07-01T01:00:00+03:00",
        )

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
