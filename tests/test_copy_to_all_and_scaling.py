from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from milky_cow.contracts import ScalingLevel, ScalingSchedule
from milky_cow.copy_to_all import (
    PAAccount,
    copy_to_all,
    settle_copy_decision,
)
from milky_cow.inputs import (
    TradeOffer,
    get_timezone,
    path_order_for_offer,
    resolve_path_order,
    select_global_one_position,
)


ZONE = get_timezone("Europe/Tallinn")


def at(label: str) -> datetime:
    return datetime.strptime(label, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZONE)


def offer(
    key: str = "offer",
    *,
    entry: str = "2026-01-02 10:00:00",
    exit: str = "2026-01-02 10:30:00",
    mae: float = -100.0,
    mfe: float = 100.0,
    pnl: float = 100.0,
    commission: float = 1.0,
    resolved: str = "mae_first",
) -> TradeOffer:
    return TradeOffer(
        trade_key=key,
        strategy_id="fixture",
        window_id="10-11",
        window_order=10,
        source_row=1,
        ticket=1,
        source_entry_label=entry,
        source_exit_label=exit,
        source_timezone_rule="Europe/Tallinn:test",
        entry_at=at(entry),
        exit_at=at(exit),
        mae_usd_per_mnq=mae,
        mfe_usd_per_mnq=mfe,
        gross_pnl_usd_per_mnq=pnl,
        candle_range=1.0,
        commission_usd_per_mnq=commission,
        resolved_path_order=resolved,
        source_file_sha256="0" * 64,
    )


def accepted_offer(trade: TradeOffer):
    selection = select_global_one_position([trade])
    return selection.accepted_opportunities[0]


def schedule(
    *,
    scope: str = "per_account",
    operator: str = "greater_than_or_equal",
    downscale: str = "immediate",
) -> ScalingSchedule:
    return ScalingSchedule(
        policy_id="fixture_schedule",
        scope=scope,
        threshold_metric="realized_balance_usd",
        levels=(
            ScalingLevel(None, 1),
            ScalingLevel(26_600.0, 2),
            ScalingLevel(28_000.0, 3),
        ),
        threshold_operator=operator,
        decision_time="entry_before_trade_after_prior_same_timestamp_events",
        downscale_rule=downscale,
        synchronized_aggregation=(
            "minimum_eligible_metric"
            if scope == "synchronized_book"
            else None
        ),
        maximum_mnq=3,
        outcome_scaling="linear_per_mnq",
    )


class CopyToAllParityTests(unittest.TestCase):
    def test_one_global_opportunity_creates_exactly_n_copies(self) -> None:
        trade = offer()
        for count in range(4):
            with self.subTest(active_pas=count):
                accounts = [
                    PAAccount(
                        pa_id=index,
                        activated_at=trade.entry_at - timedelta(seconds=1),
                    )
                    for index in range(1, count + 1)
                ]
                decision = copy_to_all(accepted_offer(trade), list(reversed(accounts)), schedule())
                self.assertEqual(decision.global_opportunity_count, 1)
                self.assertEqual(decision.account_copy_count, count)
                self.assertEqual(
                    decision.eligible_pa_ids,
                    tuple(range(1, count + 1)),
                )
                self.assertFalse(hasattr(decision, "selected_pa_ids"))

    def test_activation_at_entry_dead_pa_and_compliance_block_are_excluded(self) -> None:
        trade = offer()
        accounts = [
            PAAccount(1, trade.entry_at - timedelta(seconds=1)),
            PAAccount(2, trade.entry_at),
            PAAccount(3, trade.entry_at - timedelta(days=1), alive=False),
            PAAccount(4, trade.entry_at - timedelta(days=1)),
        ]
        decision = copy_to_all(
            accepted_offer(trade),
            accounts,
            schedule(),
            compliance_blocks={4: "explicit_contract_limit"},
        )
        self.assertEqual(decision.candidate_pa_ids, (1, 4))
        self.assertEqual(decision.eligible_pa_ids, (1,))
        self.assertEqual(
            decision.compliance_blocks,
            ((4, "explicit_contract_limit"),),
        )
        self.assertEqual(decision.account_copy_count, 1)

    def test_identical_accounts_have_correlated_threshold_touch_deaths(self) -> None:
        trade = offer(mae=-1_500.0, mfe=0.0, pnl=-100.0)
        accounts = [
            PAAccount(index, trade.entry_at - timedelta(days=1))
            for index in range(1, 4)
        ]
        decision = copy_to_all(accepted_offer(trade), accounts, schedule())
        results = settle_copy_decision(
            decision,
            {account.pa_id: account for account in accounts},
            event_at=trade.exit_at,
            path_order="resolved",
            commission_timing="close_only",
        )
        self.assertEqual(len(results), 3)
        self.assertTrue(all(not result.survived for result in results))
        self.assertEqual(
            {result.death_reason for result in results},
            {"intratrade_drawdown"},
        )
        state_tuples = {
            (
                account.equity_profit_usd,
                account.peak_profit_usd,
                account.liquidation_floor_profit_usd,
                account.alive,
            )
            for account in accounts
        }
        self.assertEqual(len(state_tuples), 1)

    def test_raw_or_blocked_offer_cannot_enter_the_pa_book(self) -> None:
        trade = offer()
        account = PAAccount(1, trade.entry_at - timedelta(days=1))
        with self.assertRaisesRegex(TypeError, "accepted opportunities"):
            copy_to_all(trade, [account], schedule())

    def test_compliance_block_cannot_silently_name_an_ineligible_pa(self) -> None:
        trade = offer()
        account = PAAccount(1, trade.entry_at)
        with self.assertRaisesRegex(ValueError, "live PAs activated before entry"):
            copy_to_all(
                accepted_offer(trade),
                [account],
                schedule(),
                compliance_blocks={1: "not_yet_active"},
            )

    def test_settlement_is_exit_bound_one_shot_and_auditable(self) -> None:
        trade = offer(pnl=100.0, commission=1.0)
        account = PAAccount(1, trade.entry_at - timedelta(days=1))
        decision = copy_to_all(accepted_offer(trade), [account], schedule())
        with self.assertRaisesRegex(ValueError, "exact exit"):
            settle_copy_decision(
                decision,
                {1: account},
                event_at=trade.exit_at - timedelta(seconds=1),
                path_order="resolved",
                commission_timing="close_only",
            )
        result = settle_copy_decision(
            decision,
            {1: account},
            event_at=trade.exit_at,
            path_order="resolved",
            commission_timing="close_only",
        )[0]
        self.assertEqual(result.event_at, trade.exit_at)
        self.assertTrue(result.completed_trade_outcome_applied)
        self.assertEqual(result.commission_usd, 1.0)
        self.assertEqual(decision.scaling_policy_id, "fixture_schedule")
        self.assertEqual(decision.copies[0].scaling_metric_usd, 25_000.0)
        with self.assertRaisesRegex(ValueError, "already been settled"):
            settle_copy_decision(
                decision,
                {1: account},
                event_at=trade.exit_at,
                path_order="resolved",
                commission_timing="close_only",
            )

    def test_state_mutation_while_a_copy_is_outstanding_is_rejected(self) -> None:
        trade = offer()
        account = PAAccount(1, trade.entry_at - timedelta(days=1))
        decision = copy_to_all(accepted_offer(trade), [account], schedule())
        account.equity_profit_usd = 1.0
        with self.assertRaisesRegex(ValueError, "changed while"):
            settle_copy_decision(
                decision,
                {1: account},
                event_at=trade.exit_at,
                path_order="resolved",
                commission_timing="close_only",
            )
        self.assertIsNone(decision.settled_at)

    def test_commission_timing_is_explicit_at_the_drawdown_boundary(self) -> None:
        trade = offer(mae=-1_499.50, mfe=0.0, pnl=0.0, commission=1.0)
        close_only = PAAccount(1, trade.entry_at - timedelta(days=1))
        intratrade = PAAccount(2, trade.entry_at - timedelta(days=1))
        close_decision = copy_to_all(accepted_offer(trade), [close_only], schedule())
        intra_decision = copy_to_all(accepted_offer(trade), [intratrade], schedule())
        close_result = settle_copy_decision(
            close_decision,
            {1: close_only},
            event_at=trade.exit_at,
            path_order="resolved",
            commission_timing="close_only",
        )[0]
        intra_result = settle_copy_decision(
            intra_decision,
            {2: intratrade},
            event_at=trade.exit_at,
            path_order="resolved",
            commission_timing="intratrade_and_close",
        )[0]
        self.assertTrue(close_result.survived)
        self.assertFalse(intra_result.survived)
        self.assertFalse(intra_result.completed_trade_outcome_applied)
        self.assertIsNone(intra_result.net_pnl_usd)

    def test_path_stress_changes_only_ambiguous_trade_order(self) -> None:
        seeded = resolve_path_order(
            datetime(2026, 1, 13, 10, 3),
            datetime(2026, 1, 13, 10, 33),
            -1_000.0,
            1_000.0,
            1.05,
        )
        self.assertEqual(seeded, "mfe_first")
        ambiguous = offer(
            "ambiguous_boundary",
            entry="2026-01-13 10:03:00",
            exit="2026-01-13 10:33:00",
            mae=-1_000.0,
            mfe=1_000.0,
            pnl=1.05,
            commission=1.05,
            resolved=seeded,
        )
        self.assertEqual(ambiguous.intratrade_path_status, "ambiguous")
        outcomes = {}
        for arm in (
            "source_constrained_then_mae_first",
            "source_constrained_then_mfe_first",
            "source_constrained_then_seeded_coin",
        ):
            account = PAAccount(
                pa_id=1,
                activated_at=ambiguous.entry_at - timedelta(days=1),
                equity_profit_usd=100.0,
                peak_profit_usd=101.05,
                liquidation_floor_profit_usd=-1_398.95,
            )
            decision = copy_to_all(accepted_offer(ambiguous), [account], schedule())
            result = settle_copy_decision(
                decision,
                {1: account},
                event_at=ambiguous.exit_at,
                path_order=path_order_for_offer(ambiguous, arm),
                commission_timing="close_only",
            )[0]
            outcomes[arm] = result.survived
        self.assertTrue(outcomes["source_constrained_then_mae_first"])
        self.assertFalse(outcomes["source_constrained_then_mfe_first"])
        self.assertFalse(outcomes["source_constrained_then_seeded_coin"])

        constrained = offer(
            "one_sided",
            mae=-100.0,
            mfe=0.0,
            pnl=-50.0,
            resolved="mae_first",
        )
        self.assertEqual(constrained.intratrade_path_status, "source_constrained")
        self.assertEqual(
            path_order_for_offer(constrained, "source_constrained_then_mae_first"),
            "mae_first",
        )
        self.assertEqual(
            path_order_for_offer(constrained, "source_constrained_then_mfe_first"),
            "mae_first",
        )
        terminal_mae = offer(
            "terminal_mae",
            mae=-100.0,
            mfe=100.0,
            pnl=-100.0,
            resolved="mfe_first",
        )
        terminal_mfe = offer(
            "terminal_mfe",
            mae=-100.0,
            mfe=100.0,
            pnl=100.0,
            resolved="mae_first",
        )
        self.assertEqual(terminal_mae.intratrade_path_status, "source_constrained")
        self.assertEqual(terminal_mfe.intratrade_path_status, "ambiguous")
        for arm in outcomes:
            self.assertEqual(path_order_for_offer(terminal_mae, arm), "mfe_first")
        self.assertEqual(
            path_order_for_offer(
                terminal_mfe,
                "source_constrained_then_mae_first",
            ),
            "mae_first",
        )
        self.assertEqual(
            path_order_for_offer(
                terminal_mfe,
                "source_constrained_then_mfe_first",
            ),
            "mfe_first",
        )
        seeded_terminal = path_order_for_offer(
            terminal_mfe,
            "source_constrained_then_seeded_coin",
        )
        self.assertIn(seeded_terminal, {"mae_first", "mfe_first"})
        self.assertEqual(
            seeded_terminal,
            path_order_for_offer(
                terminal_mfe,
                "source_constrained_then_seeded_coin",
            ),
        )


class ScalingContractTests(unittest.TestCase):
    def test_positive_integer_and_causal_schedule_fields_are_runtime_contracts(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive integer"):
            ScalingLevel(None, 1.5)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            PAAccount(True, at("2026-01-01 00:00:00"))
        with self.assertRaisesRegex(ValueError, "non-causal"):
            ScalingSchedule(
                policy_id="future_leak",
                scope="per_account",
                threshold_metric="realized_balance_usd",
                levels=(ScalingLevel(None, 1),),
                threshold_operator="greater_than_or_equal",
                decision_time="after_seeing_future_exit",
                downscale_rule="immediate",
                synchronized_aggregation=None,
                maximum_mnq=1,
                outcome_scaling="linear_per_mnq",
            )

    def test_inclusive_thresholds_and_per_account_divergence(self) -> None:
        policy = schedule()
        self.assertEqual(policy.contracts_for_metric(26_599.99), 1)
        self.assertEqual(policy.contracts_for_metric(26_600.00), 2)
        self.assertEqual(policy.contracts_for_metric(28_000.00), 3)

        trade = offer()
        low = PAAccount(
            1,
            trade.entry_at - timedelta(days=1),
            equity_profit_usd=1_599.99,
        )
        high = PAAccount(
            2,
            trade.entry_at - timedelta(days=1),
            equity_profit_usd=1_600.00,
        )
        decision = copy_to_all(accepted_offer(trade), [high, low], policy)
        self.assertEqual(
            tuple((copy.pa_id, copy.mnq) for copy in decision.copies),
            ((1, 1), (2, 2)),
        )

    def test_synchronized_minimum_metric_uses_one_common_size(self) -> None:
        trade = offer()
        accounts = [
            PAAccount(
                1,
                trade.entry_at - timedelta(days=1),
                equity_profit_usd=1_599.99,
            ),
            PAAccount(
                2,
                trade.entry_at - timedelta(days=1),
                equity_profit_usd=5_000.0,
            ),
        ]
        decision = copy_to_all(
            accepted_offer(trade),
            accounts,
            schedule(scope="synchronized_book"),
        )
        self.assertEqual(tuple(copy.mnq for copy in decision.copies), (1, 1))

    def test_sticky_downscale_and_linear_outcomes_are_explicit(self) -> None:
        policy = schedule(downscale="sticky_max")
        self.assertEqual(
            policy.contracts_for_metric(25_000.0, prior_mnq=2),
            2,
        )
        trade = offer(pnl=100.0, commission=1.0)
        account = PAAccount(
            1,
            trade.entry_at - timedelta(days=1),
            equity_profit_usd=1_600.0,
        )
        decision = copy_to_all(accepted_offer(trade), [account], schedule())
        self.assertEqual(decision.copies[0].mnq, 2)
        result = settle_copy_decision(
            decision,
            {account.pa_id: account},
            event_at=trade.exit_at,
            path_order="resolved",
            commission_timing="close_only",
        )[0]
        self.assertEqual(result.net_pnl_usd, 198.0)
        self.assertEqual(account.equity_profit_usd, 1_798.0)


if __name__ == "__main__":
    unittest.main()
