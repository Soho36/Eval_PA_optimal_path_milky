"""Legacy 25K PA drawdown state under completed-trade excursions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .models import PathOrder, TradeOffer, money
from .rules import Legacy25KRules


@dataclass(slots=True)
class PAState:
    pa_id: int
    activated_at: datetime
    available_after: datetime
    equity_profit_usd: float = 0.0
    peak_profit_usd: float = 0.0
    liquidation_floor_profit_usd: float = -1_500.0
    alive: bool = True
    busy: bool = False
    assigned_count: int = 0
    completed_count: int = 0
    payout_count: int = 0
    cumulative_gross_payouts_usd: float = 0.0
    cumulative_net_payouts_usd: float = 0.0
    accumulated_profit_bank_usd: float = 0.0
    payout_period_daily_pnl: dict[date, float] = field(default_factory=dict)

    @classmethod
    def create(cls, pa_id: int, activated_at: datetime, rules: Legacy25KRules) -> "PAState":
        return cls(
            pa_id=pa_id,
            activated_at=activated_at,
            available_after=activated_at,
            liquidation_floor_profit_usd=money(-rules.pa_trailing_drawdown_usd),
        )

    @property
    def headroom_usd(self) -> float:
        return money(self.equity_profit_usd - self.liquidation_floor_profit_usd)

    @property
    def nominal_balance_usd(self) -> float:
        return money(25_000.0 + self.equity_profit_usd)


@dataclass(frozen=True, slots=True)
class PATradeResult:
    pa_id: int
    trade_key: str
    survived: bool
    death_reason: str | None
    net_pnl_usd: float
    equity_before_usd: float
    equity_after_usd: float
    floor_before_usd: float
    floor_after_usd: float


def _breached(value: float, floor: float, touch_fails: bool) -> bool:
    return value <= floor if touch_fails else value < floor


def _lift_peak(pa: PAState, rules: Legacy25KRules, value: float) -> None:
    pa.peak_profit_usd = money(max(pa.peak_profit_usd, value))
    pa.liquidation_floor_profit_usd = money(
        min(
            pa.peak_profit_usd - rules.pa_trailing_drawdown_usd,
            rules.pa_frozen_floor_profit_usd,
        )
    )


def apply_pa_trade(
    pa: PAState,
    offer: TradeOffer,
    rules: Legacy25KRules,
    *,
    path_order: PathOrder,
) -> PATradeResult:
    """Settle one one-MNQ routed trade on one PA."""

    if not pa.alive:
        raise ValueError("Cannot trade a dead PA")
    before_equity = pa.equity_profit_usd
    before_floor = pa.liquidation_floor_profit_usd
    # Pinned Accounts_staggering parity: floating MAE/MFE are used as exported;
    # round-turn commission is charged only in closing net P&L.
    adverse = money(pa.equity_profit_usd + min(offer.mae_usd, 0.0))
    favorable = money(pa.equity_profit_usd + max(offer.mfe_usd, 0.0))
    closing = money(pa.equity_profit_usd + offer.net_pnl_usd)

    if path_order == "mfe_first":
        _lift_peak(pa, rules, favorable)
    if _breached(adverse, pa.liquidation_floor_profit_usd, rules.pa_threshold_touch_fails):
        pa.alive = False
        pa.busy = False
        return PATradeResult(
            pa_id=pa.pa_id,
            trade_key=offer.trade_key,
            survived=False,
            death_reason="intratrade_drawdown",
            net_pnl_usd=offer.net_pnl_usd,
            equity_before_usd=before_equity,
            equity_after_usd=pa.equity_profit_usd,
            floor_before_usd=before_floor,
            floor_after_usd=pa.liquidation_floor_profit_usd,
        )
    if path_order == "mae_first":
        _lift_peak(pa, rules, favorable)
    pa.equity_profit_usd = closing
    _lift_peak(pa, rules, closing)
    if _breached(
        pa.equity_profit_usd,
        pa.liquidation_floor_profit_usd,
        rules.pa_threshold_touch_fails,
    ):
        pa.alive = False
        pa.busy = False
        reason = "closing_drawdown"
    else:
        reason = None
        pa.completed_count += 1
        pa.accumulated_profit_bank_usd = money(
            max(0.0, pa.accumulated_profit_bank_usd + offer.net_pnl_usd)
        )
        # Payout days book realized P&L on the local exit date. Evaluation day
        # counting separately uses the accepted-entry date for upstream parity.
        day = offer.exit_trading_day
        pa.payout_period_daily_pnl[day] = money(
            pa.payout_period_daily_pnl.get(day, 0.0) + offer.net_pnl_usd
        )
    pa.busy = False
    return PATradeResult(
        pa_id=pa.pa_id,
        trade_key=offer.trade_key,
        survived=pa.alive,
        death_reason=reason,
        net_pnl_usd=offer.net_pnl_usd,
        equity_before_usd=before_equity,
        equity_after_usd=pa.equity_profit_usd,
        floor_before_usd=before_floor,
        floor_after_usd=pa.liquidation_floor_profit_usd,
    )
