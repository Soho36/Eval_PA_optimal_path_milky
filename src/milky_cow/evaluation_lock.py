"""Pinned EODMAE Evaluation behavior lock, not the integrated consumer choice.

Implementation provenance:
- parent repository I:/PycharmProjects/Eval_PA_optimal_path
- parent revision 106cfb782c6e573856282095441bb69f23924a55
- reference/shared_source/evaluation.py SHA-256
  d16bb367141d8c44e90924d7c20b5679a2d353dc122b0b298e66ab8e1dfcbeb4

The active lifecycle must not call this oracle until evaluation_consumer_mode is
explicitly resolved in config/milky_cow_contract_gate.json.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .inputs import TradeOffer, money


@dataclass(frozen=True, slots=True)
class EvaluationBehaviorRules:
    target_profit_usd: float = 1_500.0
    trailing_drawdown_usd: float = 1_500.0
    fee_usd: float = 35.0
    contracts_mnq: int = 3
    minimum_trading_days: int = 1
    cycle_days: int = 30
    threshold_touch_fails: bool = True
    carries_if_alive_at_renewal: bool = True

    def __post_init__(self) -> None:
        if any(
            value <= 0
            for value in (
                self.target_profit_usd,
                self.trailing_drawdown_usd,
                self.fee_usd,
                self.contracts_mnq,
                self.minimum_trading_days,
                self.cycle_days,
            )
        ):
            raise ValueError("Evaluation behavior-lock values must be positive")


@dataclass(slots=True)
class _EvaluationState:
    profit_usd: float
    peak_profit_usd: float
    floor_profit_usd: float
    trading_days: set[date] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class EvaluationFeeEvent:
    event_at: datetime
    event_type: str
    fee_usd: float
    cycle_number: int


@dataclass(frozen=True, slots=True)
class EvaluationBehaviorOutcome:
    start_at: datetime
    horizon_at: datetime
    status: str
    pass_at: datetime | None
    fee_events: tuple[EvaluationFeeEvent, ...]
    trades: int
    blocked_offers: int
    boundary_skips: int
    failures_dd: int
    carried_renewals: int
    terminal_profit_usd: float
    terminal_peak_usd: float
    terminal_floor_usd: float

    @property
    def evaluation_fees_usd(self) -> float:
        return money(sum(event.fee_usd for event in self.fee_events))

    @property
    def attempts(self) -> int:
        return sum(
            event.event_type in {"purchase", "renewal"}
            for event in self.fee_events
        )


def _breached(value: float, floor: float, touch_fails: bool) -> bool:
    return value <= floor if touch_fails else value < floor


def _lift_peak(
    state: _EvaluationState,
    rules: EvaluationBehaviorRules,
    value: float,
) -> None:
    state.peak_profit_usd = money(max(state.peak_profit_usd, value))
    state.floor_profit_usd = money(
        state.peak_profit_usd - rules.trailing_drawdown_usd
    )


def _apply_trade(
    state: _EvaluationState,
    offer: TradeOffer,
    rules: EvaluationBehaviorRules,
    path_mode: str,
) -> str:
    contracts = rules.contracts_mnq
    cost = money(contracts * offer.commission_usd_per_mnq)
    adverse = money(
        state.profit_usd
        + contracts * min(offer.mae_usd_per_mnq, 0.0)
        - cost
    )
    favorable = money(
        state.profit_usd
        + contracts * max(offer.mfe_usd_per_mnq, 0.0)
        - cost
    )
    closing = money(
        state.profit_usd
        + contracts * offer.gross_pnl_usd_per_mnq
        - cost
    )
    order = offer.resolved_path_order if path_mode == "resolved" else path_mode
    if order not in {"mae_first", "mfe_first"}:
        raise ValueError("Unsupported Evaluation path mode")

    if order == "mfe_first":
        _lift_peak(state, rules, favorable)
    if _breached(adverse, state.floor_profit_usd, rules.threshold_touch_fails):
        return "failed_dd"
    if order == "mae_first":
        _lift_peak(state, rules, favorable)
    if _breached(closing, state.floor_profit_usd, rules.threshold_touch_fails):
        return "failed_dd"
    state.profit_usd = closing
    _lift_peak(state, rules, closing)
    state.trading_days.add(offer.entry_trading_day)
    if (
        state.profit_usd >= rules.target_profit_usd
        and len(state.trading_days) >= rules.minimum_trading_days
    ):
        return "passed"
    return "active"


def simulate_eodmae_evaluation_lock(
    offers: list[TradeOffer],
    start_at: datetime,
    horizon_at: datetime,
    rules: EvaluationBehaviorRules = EvaluationBehaviorRules(),
    *,
    path_mode: str = "resolved",
) -> EvaluationBehaviorOutcome:
    """Reproduce the pinned per-Evaluation/per-cycle raw-offer adapter."""

    if start_at.tzinfo is None or horizon_at.tzinfo is None:
        raise ValueError("Evaluation bounds must be timezone-aware")
    if horizon_at <= start_at:
        raise ValueError("Evaluation horizon must follow its start")
    if path_mode not in {"resolved", "mae_first", "mfe_first"}:
        raise ValueError("Unsupported Evaluation path mode")

    ordered = sorted(
        offers,
        key=lambda row: (
            row.entry_at,
            row.window_order,
            row.source_row,
            row.ticket,
        ),
    )
    entries = [offer.entry_at for offer in ordered]
    fee_events: list[EvaluationFeeEvent] = []
    trades = blocked = boundary_skips = failures = carried = 0
    cycle_start = start_at
    state: _EvaluationState | None = None
    terminal = _EvaluationState(
        profit_usd=0.0,
        peak_profit_usd=0.0,
        floor_profit_usd=money(-rules.trailing_drawdown_usd),
    )
    cycle_number = 0

    while cycle_start < horizon_at:
        cycle_number += 1
        event_type = "purchase" if cycle_number == 1 else "renewal"
        fee_events.append(
            EvaluationFeeEvent(
                cycle_start,
                event_type,
                rules.fee_usd,
                cycle_number,
            )
        )
        if state is None:
            state = _EvaluationState(
                profit_usd=0.0,
                peak_profit_usd=0.0,
                floor_profit_usd=money(-rules.trailing_drawdown_usd),
            )
        elif rules.carries_if_alive_at_renewal:
            carried += 1
        else:
            state = _EvaluationState(
                profit_usd=0.0,
                peak_profit_usd=0.0,
                floor_profit_usd=money(-rules.trailing_drawdown_usd),
            )

        cycle_end = min(
            cycle_start + timedelta(days=rules.cycle_days),
            horizon_at,
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
            outcome = _apply_trade(state, offer, rules, path_mode)
            trades += 1
            if outcome == "passed":
                fee_events.append(
                    EvaluationFeeEvent(
                        offer.exit_at,
                        "passed",
                        0.0,
                        cycle_number,
                    )
                )
                return EvaluationBehaviorOutcome(
                    start_at,
                    horizon_at,
                    "passed",
                    offer.exit_at,
                    tuple(fee_events),
                    trades,
                    blocked,
                    boundary_skips,
                    failures,
                    carried,
                    state.profit_usd,
                    state.peak_profit_usd,
                    state.floor_profit_usd,
                )
            if outcome == "failed_dd":
                failures += 1
                failed = True
                break
            index += 1

        terminal = state
        if failed:
            state = None
        cycle_start += timedelta(days=rules.cycle_days)

    return EvaluationBehaviorOutcome(
        start_at,
        horizon_at,
        "censored",
        None,
        tuple(fee_events),
        trades,
        blocked,
        boundary_skips,
        failures,
        carried,
        terminal.profit_usd,
        terminal.peak_profit_usd,
        terminal.floor_profit_usd,
    )
