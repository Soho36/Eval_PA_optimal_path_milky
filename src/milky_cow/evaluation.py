"""Stateful, treasury-independent Legacy 25K Evaluation mechanics.

Implementation provenance:
- reviewed parent repository at revision
  106cfb782c6e573856282095441bb69f23924a55
- reference/shared_source/evaluation.py SHA-256
  d16bb367141d8c44e90924d7c20b5679a2d353dc122b0b298e66ab8e1dfcbeb4

Unlike the aggregate behavior-lock oracle, this module never creates or pays a
fee. The lifecycle coordinator must fund a purchase or renewal before creating
or renewing an Evaluation. The caller also supplies the opportunity consumer,
so this primitive does not decide whole-stream versus cycle-local selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import math
from typing import Literal

from .inputs import PathOrder, TradeOffer, money


EvaluationStatus = Literal["active", "failed", "passed"]


@dataclass(frozen=True, slots=True)
class EvaluationRules:
    target_profit_usd: float = 1_500.0
    trailing_drawdown_usd: float = 1_500.0
    contracts_mnq: int = 3
    minimum_trading_days: int = 1
    cycle_days: int = 30
    threshold_touch_fails: bool = True
    carries_if_alive_at_renewal: bool = True

    def __post_init__(self) -> None:
        amounts = (self.target_profit_usd, self.trailing_drawdown_usd)
        if not all(math.isfinite(value) and value > 0 for value in amounts):
            raise ValueError("Evaluation target and drawdown must be finite and positive")
        counts = (self.contracts_mnq, self.minimum_trading_days, self.cycle_days)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in counts
        ):
            raise ValueError("Evaluation counts must be positive integers")
        if not isinstance(self.threshold_touch_fails, bool) or not isinstance(
            self.carries_if_alive_at_renewal, bool
        ):
            raise ValueError("Evaluation rule flags must be boolean")


@dataclass(frozen=True, slots=True)
class EvaluationTrade:
    offer: TradeOffer
    entry_profit_usd: float
    entry_peak_profit_usd: float
    entry_floor_profit_usd: float


@dataclass(slots=True)
class EvaluationAccount:
    evaluation_id: str
    purchased_at: datetime
    cycle_started_at: datetime
    cycle_number: int = 1
    status: EvaluationStatus = "active"
    profit_usd: float = 0.0
    peak_profit_usd: float = 0.0
    floor_profit_usd: float = -1_500.0
    trading_days: set[date] = field(default_factory=set)
    outstanding_trade: EvaluationTrade | None = None
    pass_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.evaluation_id:
            raise ValueError("Evaluation identity is required")
        if self.purchased_at.tzinfo is None or self.cycle_started_at.tzinfo is None:
            raise ValueError("Evaluation timestamps must be timezone-aware")
        if self.cycle_started_at < self.purchased_at:
            raise ValueError("Evaluation cycle cannot predate purchase")
        if (
            not isinstance(self.cycle_number, int)
            or isinstance(self.cycle_number, bool)
            or self.cycle_number <= 0
        ):
            raise ValueError("Evaluation cycle number must be positive")
        if self.status not in {"active", "failed", "passed"}:
            raise ValueError("Unsupported Evaluation status")
        if not all(
            math.isfinite(value)
            for value in (self.profit_usd, self.peak_profit_usd, self.floor_profit_usd)
        ):
            raise ValueError("Evaluation monetary state must be finite")

    def cycle_due_at(self, rules: EvaluationRules) -> datetime:
        return self.cycle_started_at + timedelta(days=rules.cycle_days)


@dataclass(frozen=True, slots=True)
class EvaluationTradeResult:
    event_at: datetime
    evaluation_id: str
    trade_key: str
    status: EvaluationStatus
    completed_trade_outcome_applied: bool
    net_pnl_usd: float | None
    path_order: PathOrder
    profit_after_usd: float
    floor_after_usd: float


def _breached(value: float, floor: float, touch_fails: bool) -> bool:
    return value <= floor if touch_fails else value < floor


def _lift_peak(
    account: EvaluationAccount,
    rules: EvaluationRules,
    value: float,
) -> None:
    account.peak_profit_usd = money(max(account.peak_profit_usd, value))
    account.floor_profit_usd = money(
        account.peak_profit_usd - rules.trailing_drawdown_usd
    )


def begin_evaluation_trade(
    account: EvaluationAccount,
    offer: TradeOffer,
    rules: EvaluationRules = EvaluationRules(),
) -> EvaluationTrade:
    if account.status != "active":
        raise ValueError("Only an active Evaluation can accept a trade")
    if account.outstanding_trade is not None:
        raise ValueError("Evaluation already has an outstanding trade")
    if offer.entry_at < account.cycle_started_at:
        raise ValueError("Evaluation trade entry precedes the current cycle")
    if offer.entry_at >= account.cycle_due_at(rules):
        raise ValueError("Evaluation trade entry is outside the funded cycle")
    if offer.exit_at > account.cycle_due_at(rules):
        raise ValueError("Evaluation trade crosses the funded cycle boundary")
    trade = EvaluationTrade(
        offer=offer,
        entry_profit_usd=account.profit_usd,
        entry_peak_profit_usd=account.peak_profit_usd,
        entry_floor_profit_usd=account.floor_profit_usd,
    )
    account.outstanding_trade = trade
    return trade


def settle_evaluation_trade(
    account: EvaluationAccount,
    *,
    event_at: datetime,
    path_order: PathOrder,
    rules: EvaluationRules = EvaluationRules(),
) -> EvaluationTradeResult:
    trade = account.outstanding_trade
    if trade is None:
        raise ValueError("Evaluation has no outstanding trade")
    offer = trade.offer
    if event_at.tzinfo is None or event_at != offer.exit_at:
        raise ValueError("Evaluation trade must settle at its exact exit")
    if path_order not in {"mae_first", "mfe_first"}:
        raise ValueError("Unsupported Evaluation path order")
    observed = (account.profit_usd, account.peak_profit_usd, account.floor_profit_usd)
    expected = (
        trade.entry_profit_usd,
        trade.entry_peak_profit_usd,
        trade.entry_floor_profit_usd,
    )
    if observed != expected:
        raise ValueError("Evaluation state changed while a trade was outstanding")

    contracts = rules.contracts_mnq
    commission = money(contracts * offer.commission_usd_per_mnq)
    adverse = money(
        account.profit_usd
        + contracts * min(offer.mae_usd_per_mnq, 0.0)
        - commission
    )
    favorable = money(
        account.profit_usd
        + contracts * max(offer.mfe_usd_per_mnq, 0.0)
        - commission
    )
    closing = money(
        account.profit_usd
        + contracts * offer.gross_pnl_usd_per_mnq
        - commission
    )
    account.outstanding_trade = None

    if path_order == "mfe_first":
        _lift_peak(account, rules, favorable)
    if _breached(adverse, account.floor_profit_usd, rules.threshold_touch_fails):
        account.status = "failed"
        return EvaluationTradeResult(
            event_at,
            account.evaluation_id,
            offer.trade_key,
            account.status,
            False,
            None,
            path_order,
            account.profit_usd,
            account.floor_profit_usd,
        )
    if path_order == "mae_first":
        _lift_peak(account, rules, favorable)
    if _breached(closing, account.floor_profit_usd, rules.threshold_touch_fails):
        account.status = "failed"
        return EvaluationTradeResult(
            event_at,
            account.evaluation_id,
            offer.trade_key,
            account.status,
            False,
            None,
            path_order,
            account.profit_usd,
            account.floor_profit_usd,
        )

    net = money(contracts * offer.gross_pnl_usd_per_mnq - commission)
    account.profit_usd = closing
    _lift_peak(account, rules, closing)
    account.trading_days.add(offer.entry_trading_day)
    if (
        account.profit_usd >= rules.target_profit_usd
        and len(account.trading_days) >= rules.minimum_trading_days
    ):
        account.status = "passed"
        account.pass_at = event_at
    return EvaluationTradeResult(
        event_at,
        account.evaluation_id,
        offer.trade_key,
        account.status,
        True,
        net,
        path_order,
        account.profit_usd,
        account.floor_profit_usd,
    )


def renew_evaluation(
    account: EvaluationAccount,
    event_at: datetime,
    rules: EvaluationRules = EvaluationRules(),
) -> None:
    """Advance one already-funded cycle; funding is the caller's responsibility."""

    if event_at.tzinfo is None or event_at != account.cycle_due_at(rules):
        raise ValueError("Evaluation renewal must occur at the exact cycle boundary")
    if account.status == "passed" or account.outstanding_trade is not None:
        raise ValueError("Passed or busy Evaluations cannot renew")
    account.cycle_number += 1
    account.cycle_started_at = event_at
    if account.status == "failed" or not rules.carries_if_alive_at_renewal:
        account.profit_usd = 0.0
        account.peak_profit_usd = 0.0
        account.floor_profit_usd = money(-rules.trailing_drawdown_usd)
        account.trading_days.clear()
    account.status = "active"
