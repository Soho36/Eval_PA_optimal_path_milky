from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from milky_cow.inputs import get_timezone
from milky_cow.treasury import ExternalCapitalPolicy, Treasury


TALLINN = get_timezone("Europe/Tallinn")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=TALLINN)


def first_pa_chain_policy() -> ExternalCapitalPolicy:
    return ExternalCapitalPolicy(
        policy_id="first_pa_chain_only",
        mode="first_pa_chain_only",
        permitted_uses=("evaluation_renewal", "pa_activation"),
        lifetime_cap_usd=None,
        contribution_timing="just_in_time_exact_shortfall",
        close_event="bridge_evaluation_activated",
        reopens=False,
        bridge_evaluation_id="eval-1",
    )


class FirstPaChainCapitalTests(unittest.TestCase):
    def test_only_bootstrap_renewal_and_activation_receive_bridge_capital(
        self,
    ) -> None:
        treasury = Treasury(starting_cash_usd=35.0)
        policy = first_pa_chain_policy()
        start = at("2026-01-01 01:00:00")

        # Starting cash, never the bridge, purchases the bootstrap Evaluation.
        self.assertTrue(
            treasury.fund_and_pay_fee(
                start, 35.0, "evaluation_purchase", "eval-1", policy
            )
        )
        self.assertEqual(treasury.external_contributions_usd, 0.0)
        ledger_before = tuple(treasury.ledger)
        for purpose, amount in (
            ("evaluation_purchase", 35.0),
            ("evaluation_renewal", 35.0),
            ("pa_activation", 125.0),
        ):
            self.assertFalse(
                treasury.fund_and_pay_fee(
                    start + timedelta(minutes=2),
                    amount,
                    purpose,
                    "eval-2",
                    policy,
                )
            )
            self.assertEqual(tuple(treasury.ledger), ledger_before)

        self.assertTrue(
            treasury.fund_and_pay_fee(
                start + timedelta(minutes=3),
                35.0,
                "evaluation_renewal",
                "eval-1",
                policy,
            )
        )
        self.assertTrue(
            treasury.fund_and_pay_fee(
                start + timedelta(minutes=4),
                125.0,
                "pa_activation",
                "eval-1",
                policy,
            )
        )
        self.assertEqual(treasury.external_contributions_usd, 160.0)

        treasury.observe_pa_activation(start + timedelta(minutes=4), "eval-1")
        self.assertTrue(treasury.external_bridge_closed_for(policy))
        closed_ledger = tuple(treasury.ledger)
        self.assertFalse(
            treasury.fund_and_pay_fee(
                start + timedelta(minutes=5),
                35.0,
                "evaluation_renewal",
                "eval-1",
                policy,
            )
        )
        self.assertEqual(tuple(treasury.ledger), closed_ledger)
        treasury.assert_integrity()

    def test_other_pa_activation_does_not_close_bootstrap_lineage_bridge(
        self,
    ) -> None:
        treasury = Treasury(starting_cash_usd=195.0)
        policy = first_pa_chain_policy()
        start = at("2026-01-01 01:00:00")

        self.assertTrue(
            treasury.fund_and_pay_fee(
                start, 35.0, "evaluation_purchase", "eval-1", policy
            )
        )
        self.assertTrue(
            treasury.fund_and_pay_fee(
                start + timedelta(minutes=1),
                35.0,
                "evaluation_purchase",
                "eval-2",
                policy,
            )
        )
        self.assertTrue(
            treasury.fund_and_pay_fee(
                start + timedelta(minutes=2),
                125.0,
                "pa_activation",
                "eval-2",
                policy,
            )
        )
        treasury.observe_pa_activation(start + timedelta(minutes=2), "eval-2")
        self.assertTrue(treasury.external_bridge_closed)
        self.assertFalse(treasury.external_bridge_closed_for(policy))

        # Global first-PA time is not the authorization key. Eval 1's explicit
        # lineage remains eligible until that Evaluation itself activates.
        self.assertTrue(
            treasury.fund_and_pay_fee(
                start + timedelta(minutes=3),
                35.0,
                "evaluation_renewal",
                "eval-1",
                policy,
            )
        )
        self.assertEqual(treasury.external_contributions_usd, 35.0)
        treasury.assert_integrity()

    def test_first_chain_policy_requires_identity_and_narrow_uses(self) -> None:
        common = dict(
            policy_id="invalid_first_chain",
            mode="first_pa_chain_only",
            lifetime_cap_usd=None,
            contribution_timing="just_in_time_exact_shortfall",
            close_event="bridge_evaluation_activated",
            reopens=False,
        )
        with self.assertRaisesRegex(ValueError, "explicit bridge Evaluation id"):
            ExternalCapitalPolicy(
                permitted_uses=("evaluation_renewal", "pa_activation"),
                **common,
            )
        with self.assertRaisesRegex(
            ValueError, "only bootstrap renewal and activation"
        ):
            ExternalCapitalPolicy(
                permitted_uses=(
                    "evaluation_purchase",
                    "evaluation_renewal",
                    "pa_activation",
                ),
                bridge_evaluation_id="eval-1",
                **common,
            )


if __name__ == "__main__":
    unittest.main()
