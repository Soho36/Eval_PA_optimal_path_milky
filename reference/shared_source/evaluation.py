"""Legacy 25K Evaluation engine using the pinned fill-time behavior proxy."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .models import TradeOffer, money
from .rules import Legacy25KRules


@dataclass(slots=True)
class EvaluationState:
    balance_usd: float
    peak_equity_usd: float
    floor_usd: float
    trading_days: set[date] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class EvaluationEvent:
    event_at: datetime
    event_type: str
    fee_usd: float = 0.0
    cycle_number: int = 0


@dataclass(frozen=True, slots=True)
class EvaluationTradeTrace:
    trade_key: str
    entry_at: datetime
    exit_at: datetime
    balance_before_usd: float
    balance_after_usd: float
    peak_before_usd: float
    peak_after_usd: float
    floor_before_usd: float
    floor_after_usd: float
    outcome: str


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    start_at: datetime
    horizon_at: datetime
    status: str
    pass_at: datetime | None
    fee_events: tuple[EvaluationEvent, ...]
    trades: int
    blocked_offers: int
    boundary_skips: int
    failures_dd: int
    carried_renewals: int
    terminal_balance_usd: float
    terminal_peak_usd: float
    terminal_floor_usd: float
    trade_trace: tuple[EvaluationTradeTrace, ...] = ()

    @property
    def evaluation_fees_usd(self) -> float:
        return money(sum(event.fee_usd for event in self.fee_events))

    @property
    def attempts(self) -> int:
        return sum(event.event_type in {"purchase", "renewal"} for event in self.fee_events)


def _breached(value: float, floor: float, touch_fails: bool) -> bool:
    return value <= floor if touch_fails else value < floor


def _lift_peak(state: EvaluationState, rules: Legacy25KRules, value: float) -> None:
    state.peak_equity_usd = money(max(state.peak_equity_usd, value))
    # This deliberately locks the pinned Legacy Evaluation behavior. The floor
    # never freezes; alternative firm interpretations belong in a sensitivity.
    state.floor_usd = money(
        state.peak_equity_usd - rules.evaluation_trailing_drawdown_usd
    )


def _apply_trade(
    state: EvaluationState,
    offer: TradeOffer,
    rules: Legacy25KRules,
    path_mode: str,
) -> str:
    contracts = rules.evaluation_contracts_mnq
    cost = money(contracts * offer.commission_usd)
    adverse = money(state.balance_usd + contracts * min(offer.mae_usd, 0.0) - cost)
    favorable = money(state.balance_usd + contracts * max(offer.mfe_usd, 0.0) - cost)
    closing = money(state.balance_usd + contracts * offer.gross_pnl_usd - cost)
    order = offer.resolved_path_order if path_mode == "resolved" else path_mode
    if order not in {"mae_first", "mfe_first"}:
        raise ValueError(f"Unsupported path mode: {path_mode}")

    if order == "mfe_first":
        _lift_peak(state, rules, favorable)
    if _breached(adverse, state.floor_usd, rules.evaluation_threshold_touch_fails):
        return "failed_dd"
    if order == "mae_first":
        _lift_peak(state, rules, favorable)
    if _breached(closing, state.floor_usd, rules.evaluation_threshold_touch_fails):
        return "failed_dd"
    state.balance_usd = closing
    _lift_peak(state, rules, closing)
    state.trading_days.add(offer.trading_day)
    if (
        state.balance_usd >= rules.evaluation_profit_target_usd
        and len(state.trading_days) >= rules.evaluation_minimum_trading_days
    ):
        return "passed"
    return "active"


def simulate_evaluation(
    offers: list[TradeOffer],
    start_at: datetime,
    horizon_at: datetime,
    rules: Legacy25KRules,
    *,
    path_mode: str = "resolved",
    trace: bool = False,
) -> EvaluationOutcome:
    """Simulate one renewable Evaluation until pass or the supplied horizon.

    Offers are globally blocked using ``[entry_at, exit_at)`` occupancy within
    each paid 30-day interval. This reproduces EODMAE's completed-fill adapter;
    the MT5 export lacks setup/order timestamps needed for literal EA parity.
    """

    if start_at.tzinfo is None or horizon_at.tzinfo is None:
        raise ValueError("Evaluation bounds must be timezone-aware")
    if horizon_at <= start_at:
        raise ValueError("Evaluation horizon must follow its start")
    if path_mode not in {"resolved", "mae_first", "mfe_first"}:
        raise ValueError("Unsupported path_mode")
    ordered = sorted(
        offers, key=lambda row: (row.entry_at, row.window_order, row.source_row, row.ticket)
    )
    entries = [offer.entry_at for offer in ordered]
    fee_events: list[EvaluationEvent] = []
    traces: list[EvaluationTradeTrace] = []
    trades = blocked = boundary_skips = failures = carried = 0
    cycle_start = start_at
    state: EvaluationState | None = None
    terminal_state = EvaluationState(
        balance_usd=0.0,
        peak_equity_usd=0.0,
        floor_usd=money(-rules.evaluation_trailing_drawdown_usd),
    )
    cycle_number = 0

    while cycle_start < horizon_at:
        cycle_number += 1
        event_type = "purchase" if cycle_number == 1 else "renewal"
        fee_events.append(
            EvaluationEvent(
                event_at=cycle_start,
                event_type=event_type,
                fee_usd=rules.evaluation_fee_usd,
                cycle_number=cycle_number,
            )
        )
        if state is None:
            state = EvaluationState(
                balance_usd=0.0,
                peak_equity_usd=0.0,
                floor_usd=money(-rules.evaluation_trailing_drawdown_usd),
            )
        elif rules.evaluation_carries_if_alive_at_renewal:
            carried += 1
        else:
            state = EvaluationState(
                balance_usd=0.0,
                peak_equity_usd=0.0,
                floor_usd=money(-rules.evaluation_trailing_drawdown_usd),
            )

        cycle_end = min(
            cycle_start + timedelta(days=rules.evaluation_cycle_days), horizon_at
        )
        index = bisect_left(entries, cycle_start)
        open_until = cycle_start
        failed = False
        while index < len(ordered) and ordered[index].entry_at < cycle_end:
            offer = ordered[index]
            if offer.entry_at < open_until:
                blocked += 1
                index += 1
                continue
            open_until = offer.exit_at
            if offer.exit_at > cycle_end:
                boundary_skips += 1
                break
            before = (
                state.balance_usd,
                state.peak_equity_usd,
                state.floor_usd,
            )
            outcome = _apply_trade(state, offer, rules, path_mode)
            trades += 1
            if trace:
                traces.append(
                    EvaluationTradeTrace(
                        trade_key=offer.trade_key,
                        entry_at=offer.entry_at,
                        exit_at=offer.exit_at,
                        balance_before_usd=before[0],
                        balance_after_usd=state.balance_usd,
                        peak_before_usd=before[1],
                        peak_after_usd=state.peak_equity_usd,
                        floor_before_usd=before[2],
                        floor_after_usd=state.floor_usd,
                        outcome=outcome,
                    )
                )
            if outcome == "passed":
                fee_events.append(
                    EvaluationEvent(
                        event_at=offer.exit_at,
                        event_type="passed",
                        cycle_number=cycle_number,
                    )
                )
                return EvaluationOutcome(
                    start_at=start_at,
                    horizon_at=horizon_at,
                    status="passed",
                    pass_at=offer.exit_at,
                    fee_events=tuple(fee_events),
                    trades=trades,
                    blocked_offers=blocked,
                    boundary_skips=boundary_skips,
                    failures_dd=failures,
                    carried_renewals=carried,
                    terminal_balance_usd=state.balance_usd,
                    terminal_peak_usd=state.peak_equity_usd,
                    terminal_floor_usd=state.floor_usd,
                    trade_trace=tuple(traces),
                )
            if outcome == "failed_dd":
                failures += 1
                failed = True
                break
            index += 1
        terminal_state = state
        if failed:
            state = None
        cycle_start += timedelta(days=rules.evaluation_cycle_days)

    return EvaluationOutcome(
        start_at=start_at,
        horizon_at=horizon_at,
        status="censored",
        pass_at=None,
        fee_events=tuple(fee_events),
        trades=trades,
        blocked_offers=blocked,
        boundary_skips=boundary_skips,
        failures_dd=failures,
        carried_renewals=carried,
        terminal_balance_usd=terminal_state.balance_usd,
        terminal_peak_usd=terminal_state.peak_equity_usd,
        terminal_floor_usd=terminal_state.floor_usd,
        trade_trace=tuple(traces),
    )
