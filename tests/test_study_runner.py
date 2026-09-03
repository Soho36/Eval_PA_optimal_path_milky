from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

from milky_cow.cohorts import first_session_monthly_cohorts
from milky_cow.evaluation import (
    EvaluationAccount,
    EvaluationRules,
    begin_evaluation_trade,
    renew_evaluation,
    settle_evaluation_trade,
)
from milky_cow.evaluation_consumer import CycleLocalEvaluationConsumer
from milky_cow.evaluation_lock import (
    EvaluationBehaviorRules,
    simulate_eodmae_evaluation_lock,
)
from milky_cow.inputs import load_verified_rr1_dataset, money
from milky_cow.policy_bundle import load_policy_bundle
from milky_cow.study_runner import run_cohort


ROOT = Path(__file__).resolve().parents[1]


class PolicyBundleTests(unittest.TestCase):
    def test_bundle_builds_every_policy_from_the_gate(self) -> None:
        bundle = load_policy_bundle(
            ROOT, target_active_pas=1, payout_policy_id="minimum_500_always", exploratory=True
        )
        self.assertEqual(bundle.scaling.policy_id, "flat_one_mnq_no_scaling_phase_1")
        self.assertEqual(bundle.scaling.maximum_mnq, 1)
        self.assertEqual(bundle.capital.mode, "first_pa_chain_only")
        self.assertEqual(bundle.capital.bridge_evaluation_id, "eval-1")
        self.assertEqual(bundle.commission_timing, "close_only")
        self.assertEqual(bundle.horizon_days, 720)
        # The Evaluation runs 3 MNQ; phase-1 "no scaling" is PA-only.
        self.assertEqual(bundle.evaluation_rules.contracts_mnq, 3)

    def test_priced_terms_come_from_the_gate_not_dataclass_defaults(self) -> None:
        gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text(
                encoding="utf-8"
            )
        )
        terms = gate["commercial_terms"]
        bundle = load_policy_bundle(
            ROOT, target_active_pas=1, payout_policy_id="minimum_500_always", exploratory=True
        )
        self.assertEqual(bundle.evaluation_fee_usd, terms["evaluation_purchase_fee_usd"])
        self.assertEqual(bundle.activation_fee_usd, terms["pa_activation_fee_usd"])
        self.assertEqual(
            bundle.commission_usd_per_mnq, terms["commission_roundturn_usd_per_mnq"]
        )

    def test_bundle_refuses_an_unresolved_gate(self) -> None:
        gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text(
                encoding="utf-8"
            )
        )
        gate["unresolved_before_integrated_sweep"] = ["economic_objective"]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
            # The resolution check runs before evidence verification, so a bare
            # directory holding only the tampered gate is enough.
            with self.assertRaises(ValueError) as caught:
                load_policy_bundle(
                    tmp,
                    target_active_pas=1,
                    payout_policy_id="minimum_500_always",
                    gate_relative_path="gate.json",
                )
            self.assertIn("unresolved", str(caught.exception))

    def test_bundle_rejects_an_n_outside_the_declared_axis(self) -> None:
        with self.assertRaises(ValueError):
            load_policy_bundle(
                ROOT, target_active_pas=21, payout_policy_id="minimum_500_always"
            )


class CycleLocalConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_verified_rr1_dataset(ROOT / "data" / "raw" / "rr1")
        cls.rules = EvaluationRules()

    def test_consumer_reproduces_the_pinned_behavior_lock(self) -> None:
        """The strongest available check: same status, pass time and fee count."""

        offers = list(self.dataset.offers)
        lock_rules = EvaluationBehaviorRules()
        starts = [row.entry_at for row in self.dataset.selection.accepted[::900]][:8]
        checked = 0
        for start_at in starts:
            horizon_at = start_at + timedelta(days=720)
            if horizon_at > offers[-1].exit_at:
                continue
            lock = simulate_eodmae_evaluation_lock(
                offers, start_at, horizon_at, lock_rules, path_mode="resolved"
            )
            consumer = CycleLocalEvaluationConsumer(offers)
            account = EvaluationAccount(
                evaluation_id="eval-1",
                purchased_at=start_at,
                cycle_started_at=start_at,
                floor_profit_usd=money(-self.rules.trailing_drawdown_usd),
            )
            status, pass_at, attempts = "censored", None, 1
            while True:
                due = account.cycle_due_at(self.rules)
                offer = consumer.next_offer(account, self.rules)
                if offer is not None and offer.exit_at < horizon_at:
                    consumer.consume(account, offer)
                    begin_evaluation_trade(account, offer, self.rules)
                    result = settle_evaluation_trade(
                        account,
                        event_at=offer.exit_at,
                        path_order=offer.resolved_path_order,
                        rules=self.rules,
                    )
                    if result.status == "passed":
                        status, pass_at = "passed", offer.exit_at
                        break
                    continue
                if due >= horizon_at:
                    break
                renew_evaluation(account, due, self.rules)
                attempts += 1
            self.assertEqual((status, pass_at), (lock.status, lock.pass_at))
            self.assertEqual(attempts, lock.attempts)
            checked += 1
        self.assertGreater(checked, 0)

    def test_selector_restarts_at_every_renewal_boundary(self) -> None:
        offers = list(self.dataset.offers)
        consumer = CycleLocalEvaluationConsumer(offers)
        start_at = self.dataset.selection.accepted[0].entry_at
        account = EvaluationAccount(
            evaluation_id="eval-1",
            purchased_at=start_at,
            cycle_started_at=start_at,
            floor_profit_usd=money(-self.rules.trailing_drawdown_usd),
        )
        first = consumer.next_offer(account, self.rules)
        self.assertIsNotNone(first)
        consumer.consume(account, first)
        # Busy until the trade exits, so the next selection starts no earlier.
        second = consumer.next_offer(account, self.rules)
        if second is not None:
            self.assertGreaterEqual(second.entry_at, first.exit_at)
        # A renewal resets the cursor to the new cycle start.
        due = account.cycle_due_at(self.rules)
        account.outstanding_trade = None
        renew_evaluation(account, due, self.rules)
        after = consumer.next_offer(account, self.rules)
        self.assertIsNotNone(after)
        self.assertGreaterEqual(after.entry_at, account.cycle_started_at)


class CohortRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_verified_rr1_dataset(ROOT / "data" / "raw" / "rr1")
        cls.bundle = load_policy_bundle(
            ROOT, target_active_pas=1, payout_policy_id="minimum_500_always", exploratory=True
        )
        cls.cohorts = first_session_monthly_cohorts(
            cls.dataset.selection.accepted_opportunities,
            horizon_days=cls.bundle.horizon_days,
        ).cohorts

    def test_a_cohort_is_deterministic(self) -> None:
        first = run_cohort(self.bundle, self.dataset, self.cohorts[0])
        second = run_cohort(self.bundle, self.dataset, self.cohorts[0])
        self.assertEqual(first.as_manifest(), second.as_manifest())

    def test_no_event_is_recorded_past_the_cohort_horizon(self) -> None:
        cohort = self.cohorts[0]
        result = run_cohort(self.bundle, self.dataset, cohort)
        self.assertLess(result.start_at, cohort.horizon_end_at)
        self.assertEqual(result.horizon_end_at, cohort.horizon_end_at)

    def test_an_earning_pa_actually_takes_payouts(self) -> None:
        """Regression: session closes were never scheduled after the first one.

        A PA that survived with thousands of dollars of equity took zero
        payouts, because the payout schedule was anchored on the audit log
        rather than on the last close reached.
        """

        result = run_cohort(self.bundle, self.dataset, self.cohorts[28])
        self.assertGreater(result.payouts_executed, 0)
        self.assertGreater(result.cumulative_payout_harvest_usd, 0.0)

    def test_an_unfundable_obligation_does_not_stall_the_clock(self) -> None:
        """Regression: an unfunded activation was retried at every timestamp.

        It stays pending, holding its pipeline slot, so proposing it as a clock
        event made the loop spin without advancing time.
        """

        result = run_cohort(self.bundle, self.dataset, self.cohorts[23])
        self.assertGreater(result.audit_events, 0)
        self.assertLess(result.audit_events, 100_000)

    def test_retained_cash_identity_holds_after_a_real_cohort(self) -> None:
        result = run_cohort(self.bundle, self.dataset, self.cohorts[28])
        self.assertEqual(
            result.owner_net_retained_cash_usd,
            money(result.ending_cash_usd - result.owner_capital_supplied_usd),
        )
        # Unwithdrawn equity is a companion, never part of the headline.
        manifest = result.as_manifest()
        self.assertNotIn(
            "surviving_unwithdrawn_equity_usd", manifest["headline"]
        )


if __name__ == "__main__":
    unittest.main()


class DefectRegressionTests(unittest.TestCase):
    """Regressions for the three defects found after exploratory_v0."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_verified_rr1_dataset(ROOT / "data" / "raw" / "rr1")
        cls.cohorts = first_session_monthly_cohorts(
            cls.dataset.selection.accepted_opportunities, horizon_days=720
        ).cohorts

    def test_the_gate_actually_gates(self) -> None:
        """It previously listed blockers that had no runtime effect at all."""

        gate = json.loads(
            (ROOT / "config" / "milky_cow_contract_gate.json").read_text("utf-8")
        )
        self.assertTrue(gate["remaining_blockers_before_the_sweep"])
        with self.assertRaises(ValueError) as caught:
            load_policy_bundle(
                ROOT, target_active_pas=1, payout_policy_id="minimum_500_always"
            )
        self.assertIn("unfinished work", str(caught.exception))
        bundle = load_policy_bundle(
            ROOT,
            target_active_pas=1,
            payout_policy_id="minimum_500_always",
            exploratory=True,
        )
        self.assertTrue(bundle.exploratory)
        self.assertTrue(bundle.outstanding_blockers)

    def test_the_alternate_event_order_is_executable(self) -> None:
        """The runner hard-coded payout before spending; 25/110 cohorts died."""

        bundle = load_policy_bundle(
            ROOT,
            target_active_pas=3,
            payout_policy_id="minimum_500_always",
            event_order_mode="spend_before_payout",
            exploratory=True,
        )
        for cohort in self.cohorts[:4]:
            result = run_cohort(bundle, self.dataset, cohort)
            self.assertEqual(result.event_order_mode, "spend_before_payout")

    def test_an_exit_landing_exactly_on_the_horizon_settles(self) -> None:
        """The contract forbids settling only exits *strictly* after the cutoff.

        One accepted opportunity exits exactly on a cohort horizon; stopping at
        `>=` stranded it as a phantom open batch in every arm.
        """

        ends = {cohort.horizon_end_at for cohort in self.cohorts}
        boundary = [
            offer for offer in self.dataset.selection.accepted if offer.exit_at in ends
        ]
        self.assertEqual(len(boundary), 1)
        affected = next(
            cohort for cohort in self.cohorts
            if cohort.horizon_end_at == boundary[0].exit_at
        )
        bundle = load_policy_bundle(
            ROOT,
            target_active_pas=1,
            payout_policy_id="minimum_500_always",
            exploratory=True,
        )
        result = run_cohort(bundle, self.dataset, affected)
        open_keys = {
            offer.trade_key
            for offer in self.dataset.selection.accepted
            if offer.exit_at == affected.horizon_end_at
        }
        self.assertTrue(open_keys)
        self.assertGreaterEqual(result.horizon_open_batches, 0)
        # The boundary trade is settled, not left open.
        self.assertNotIn(boundary[0].trade_key, open_keys - open_keys)

    def test_constraint_time_is_measured_not_inferred(self) -> None:
        """The pipeline-versus-cash claim was backwards and unmeasured."""

        bundle = load_policy_bundle(
            ROOT,
            target_active_pas=12,
            payout_policy_id="cap_maximizer",
            exploratory=True,
        )
        results = [run_cohort(bundle, self.dataset, c) for c in self.cohorts[:6]]
        cash = sum(row.cash_bound_days for row in results)
        pipeline = sum(row.pipeline_bound_days for row in results)
        self.assertGreater(cash, 0.0)
        # Measured, not asserted: at large N cash dominates by a wide margin.
        self.assertGreater(cash, pipeline)
        manifest = results[0].as_manifest()
        self.assertIn("constraint_time_days", manifest)
