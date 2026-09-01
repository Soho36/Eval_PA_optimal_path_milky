"""Shared immutable input and ledger models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal


PathOrder = Literal["mae_first", "mfe_first"]


def money(value: float) -> float:
    """Quantize a monetary value to cents, matching the pinned simulators."""

    return round(float(value), 2)


@dataclass(frozen=True, slots=True)
class TradeOffer:
    """One isolated-window completed-trade opportunity at one MNQ."""

    trade_key: str
    strategy_id: str
    window_id: str
    window_order: int
    source_row: int
    ticket: int
    source_entry_label: str
    source_exit_label: str
    source_timezone_rule: str
    entry_at: datetime
    exit_at: datetime
    mae_usd: float
    mfe_usd: float
    gross_pnl_usd: float
    candle_range: float
    commission_usd: float
    resolved_path_order: PathOrder
    source_file_sha256: str

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.source_timezone_rule:
            raise ValueError("TradeOffer strategy and timezone provenance are required")
        if self.entry_at.tzinfo is None or self.exit_at.tzinfo is None:
            raise ValueError("TradeOffer timestamps must be timezone-aware")
        if self.exit_at < self.entry_at:
            raise ValueError("TradeOffer exit precedes entry")
        if self.window_order < 1 or self.window_order > 23:
            raise ValueError("window_order must be in 1..23")
        if self.source_row < 1:
            raise ValueError("source_row must be positive")
        if self.commission_usd < 0:
            raise ValueError("commission_usd cannot be negative")

    @property
    def net_pnl_usd(self) -> float:
        return money(self.gross_pnl_usd - self.commission_usd)

    @property
    def entry_trading_day(self) -> date:
        return self.entry_at.date()

    @property
    def exit_trading_day(self) -> date:
        return self.exit_at.date()

    @property
    def trading_day(self) -> date:
        """Backward-compatible Evaluation day: the accepted-entry local date."""

        return self.entry_trading_day


@dataclass(frozen=True, slots=True)
class CashLedgerEntry:
    event_at: datetime
    kind: str
    amount_usd: float
    reference: str
    cash_after_usd: float


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    signal_key: str
    entry_at: datetime
    requested_copies: int
    filled_copies: int
    ordered_eligible_pa_ids: tuple[int, ...]
    selected_pa_ids: tuple[int, ...]
    live_k: int
    tradable_k: int
    busy_k: int
    rejection_reason: str | None
