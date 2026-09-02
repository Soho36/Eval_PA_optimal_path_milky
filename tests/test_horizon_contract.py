from datetime import datetime, timedelta, timezone
import unittest

from milky_cow.cohorts import classify_horizon_trade


class HorizonCrossingContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.horizon = datetime(2026, 1, 10, 1, 0, tzinfo=timezone.utc)

    def test_entry_before_horizon_and_exit_after_is_left_open_unscored(self) -> None:
        self.assertEqual(
            classify_horizon_trade(
                self.horizon - timedelta(minutes=1),
                self.horizon + timedelta(minutes=1),
                self.horizon,
            ),
            "leave_open_unscored",
        )

    def test_completed_outcome_at_the_horizon_is_settled(self) -> None:
        self.assertEqual(
            classify_horizon_trade(
                self.horizon - timedelta(hours=1),
                self.horizon,
                self.horizon,
            ),
            "settle_within_horizon",
        )

    def test_entry_at_horizon_is_not_admitted(self) -> None:
        self.assertEqual(
            classify_horizon_trade(
                self.horizon,
                self.horizon + timedelta(minutes=1),
                self.horizon,
            ),
            "outside_entry_window",
        )

    def test_naive_timestamp_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            classify_horizon_trade(
                self.horizon.replace(tzinfo=None),
                self.horizon,
                self.horizon,
            )


if __name__ == "__main__":
    unittest.main()
