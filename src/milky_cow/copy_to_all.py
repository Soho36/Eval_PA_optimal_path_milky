"""Copy every accepted global opportunity to every eligible active PA.

Implementation provenance:
- reviewed parent PA mechanics at revision
  106cfb782c6e573856282095441bb69f23924a55
- reference/shared_source/pa.py SHA-256
  58126203af8ea4562a11a9d01397e2400d590d0cc90c737125d3e897c73d5650

The router, busy-seat, assignment-count, standby, and fixed-one-MNQ mechanics
were deliberately replaced for this project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import math
from typing import Literal, Mapping

from .contracts import ScalingSchedule
from .execution import FRICTIONLESS, ExecutionModel
from .inputs import AcceptedOpportunity, PathOrder, TradeOffer, money


CommissionTiming = Literal["close_only", "intratrade_and_close"]
SettlementPathOrder = PathOrder | Literal["resolved"]


@dataclass(slots=True)
class PAAccount:
    pa_id: int
    activated_at: datetime
    equity_profit_usd: float = 0.0
    peak_profit_usd: float = 0.0
    liquidation_floor_profit_usd: float = -1_500.0
    alive: bool = True
    last_mnq: int = 1
    completed_count: int = 0
    realized_daily_pnl_usd: dict[date, float] = field(default_factory=dict)
    payout_period_daily_pnl_usd: dict[date, float] = field(default_factory=dict)
    payout_count: int = 0
    cumulative_gross_payouts_usd: float = 0.0
    cumulative_net_payouts_usd: float = 0.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.pa_id, int)
            or isinstance(self.pa_id, bool)
            or self.pa_id <= 0
        ):
            raise ValueError("PA ID must be a positive integer")
        if self.activated_at.tzinfo is None:
            raise ValueError("PA activation timestamp must be timezone-aware")
        if not all(
            math.isfinite(value)
            for value in (
                self.equity_profit_usd,
                self.peak_profit_usd,
                self.liquidation_floor_profit_usd,
            )
        ):
            raise ValueError("PA monetary state must be finite")
        if not isinstance(self.alive, bool):
            raise ValueError("PA alive state must be boolean")
        if (
            not isinstance(self.last_mnq, int)
            or isinstance(self.last_mnq, bool)
            or self.last_mnq <= 0
        ):
            raise ValueError("PA prior MNQ count must be a positive integer")
        if (
            not isinstance(self.completed_count, int)
            or isinstance(self.completed_count, bool)
            or self.completed_count < 0
        ):
            raise ValueError("PA completed count must be a non-negative integer")
        if (
            not isinstance(self.payout_count, int)
            or isinstance(self.payout_count, bool)
            or self.payout_count < 0
        ):
            raise ValueError("PA payout count must be a non-negative integer")
        for name, history in (
            ("realized-daily", self.realized_daily_pnl_usd),
            ("payout-period", self.payout_period_daily_pnl_usd),
        ):
            if any(
                not isinstance(day, date) or not math.isfinite(value)
                for day, value in history.items()
            ):
                raise ValueError(f"PA {name} history is invalid")
        if any(
            not math.isfinite(value) or value < 0
            for value in (
                self.cumulative_gross_payouts_usd,
                self.cumulative_net_payouts_usd,
            )
        ):
            raise ValueError("PA cumulative payout state must be finite and non-negative")

    @property
    def nominal_balance_usd(self) -> float:
        return money(25_000.0 + self.equity_profit_usd)


@dataclass(frozen=True, slots=True)
class AccountCopy:
    pa_id: int
    mnq: int
    scaling_metric_usd: float
    prior_mnq: int
    entry_equity_profit_usd: float
    entry_peak_profit_usd: float
    entry_floor_profit_usd: float

    def __post_init__(self) -> None:
        for name, value in (("PA ID", self.pa_id), ("MNQ", self.mnq), ("prior MNQ", self.prior_mnq)):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"Account-copy {name} must be a positive integer")
        if not all(
            math.isfinite(value)
            for value in (
                self.scaling_metric_usd,
                self.entry_equity_profit_usd,
                self.entry_peak_profit_usd,
                self.entry_floor_profit_usd,
            )
        ):
            raise ValueError("Account-copy entry-state snapshot must be finite")


@dataclass(slots=True)
class CopyDecision:
    opportunity: AcceptedOpportunity
    scaling_policy_id: str
    candidate_pa_ids: tuple[int, ...]
    eligible_pa_ids: tuple[int, ...]
    compliance_blocks: tuple[tuple[int, str], ...]
    copies: tuple[AccountCopy, ...]
    settled_at: datetime | None = field(init=False, default=None)

    @property
    def opportunity_key(self) -> str:
        return self.opportunity.offer.trade_key

    @property
    def entry_at(self) -> datetime:
        return self.opportunity.offer.entry_at

    @property
    def exit_at(self) -> datetime:
        return self.opportunity.offer.exit_at

    @property
    def global_opportunity_count(self) -> int:
        return 1

    @property
    def account_copy_count(self) -> int:
        return len(self.copies)

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity, AcceptedOpportunity):
            raise ValueError("Copy decision requires accepted-opportunity evidence")
        if not self.scaling_policy_id:
            raise ValueError("Copy decision requires a scaling policy identity")
        if self.candidate_pa_ids != tuple(sorted(set(self.candidate_pa_ids))):
            raise ValueError("Candidate PA identifiers must be unique and sorted")
        if self.eligible_pa_ids != tuple(sorted(set(self.eligible_pa_ids))):
            raise ValueError("Eligible PA identifiers must be unique and sorted")
        if any(
            not isinstance(pa_id, int) or isinstance(pa_id, bool) or pa_id <= 0
            for pa_id in self.candidate_pa_ids
        ):
            raise ValueError("Candidate PA identifiers must be positive integers")
        candidate_ids = set(self.candidate_pa_ids)
        eligible_ids = set(self.eligible_pa_ids)
        blocked_ids = [pa_id for pa_id, reason in self.compliance_blocks if reason]
        if len(blocked_ids) != len(self.compliance_blocks):
            raise ValueError("Compliance blocks require non-empty reasons")
        if len(blocked_ids) != len(set(blocked_ids)):
            raise ValueError("A candidate PA may be blocked only once")
        if eligible_ids | set(blocked_ids) != candidate_ids:
            raise ValueError("Every candidate PA must be copied or explicitly blocked")
        if eligible_ids & set(blocked_ids):
            raise ValueError("A PA cannot be both copied and blocked")
        if tuple(copy.pa_id for copy in self.copies) != self.eligible_pa_ids:
            raise ValueError("Every eligible PA must have exactly one copy")


@dataclass(frozen=True, slots=True)
class PATradeResult:
    event_at: datetime
    pa_id: int
    trade_key: str
    mnq: int
    survived: bool
    death_reason: str | None
    completed_trade_outcome_applied: bool
    net_pnl_usd: float | None
    commission_usd: float | None
    path_order: PathOrder
    commission_timing: CommissionTiming
    equity_before_usd: float
    equity_after_usd: float
    floor_before_usd: float
    floor_after_usd: float


def _scaling_metric(account: PAAccount, metric: str) -> float:
    if metric == "realized_balance_usd":
        return account.nominal_balance_usd
    if metric == "equity_profit_usd":
        return account.equity_profit_usd
    raise ValueError(f"Unsupported PA scaling metric: {metric}")


def _assert_copy_entry_state(account: PAAccount, copy: AccountCopy) -> None:
    observed = (
        account.equity_profit_usd,
        account.peak_profit_usd,
        account.liquidation_floor_profit_usd,
        account.last_mnq,
    )
    expected = (
        copy.entry_equity_profit_usd,
        copy.entry_peak_profit_usd,
        copy.entry_floor_profit_usd,
        copy.prior_mnq,
    )
    if observed != expected:
        raise ValueError("PA state changed while its copy batch was outstanding")


def copy_to_all(
    opportunity: AcceptedOpportunity,
    accounts: list[PAAccount],
    scaling: ScalingSchedule,
    *,
    compliance_blocks: Mapping[int, str] | None = None,
) -> CopyDecision:
    """Create one copy per eligible PA; PA-ID sort is reporting order only."""

    if not isinstance(opportunity, AcceptedOpportunity):
        raise TypeError("copy_to_all accepts only validated accepted opportunities")
    offer = opportunity.offer
    ids = [account.pa_id for account in accounts]
    if len(ids) != len(set(ids)):
        raise ValueError("PA IDs must be unique")
    blocks = dict(compliance_blocks or {})
    unknown_blocks = set(blocks) - set(ids)
    if unknown_blocks:
        raise ValueError(f"Compliance block names unknown PAs: {sorted(unknown_blocks)}")
    if any(not reason for reason in blocks.values()):
        raise ValueError("Compliance blocks require a non-empty reason")

    candidates = sorted(
        account.pa_id
        for account in accounts
        if account.alive and account.activated_at < offer.entry_at
    )
    ineligible_blocks = set(blocks) - set(candidates)
    if ineligible_blocks:
        raise ValueError(
            "Compliance blocks may name only live PAs activated before entry: "
            f"{sorted(ineligible_blocks)}"
        )
    eligible = [pa_id for pa_id in candidates if pa_id not in blocks]
    by_id = {account.pa_id: account for account in accounts}
    metrics = {
        pa_id: _scaling_metric(by_id[pa_id], scaling.threshold_metric)
        for pa_id in eligible
    }
    prior = {pa_id: by_id[pa_id].last_mnq for pa_id in eligible}
    sizes = scaling.contracts_for_accounts(
        metrics, prior_mnq_by_pa_id=prior
    )
    copies = tuple(
        AccountCopy(
            pa_id=pa_id,
            mnq=sizes[pa_id],
            scaling_metric_usd=metrics[pa_id],
            prior_mnq=prior[pa_id],
            entry_equity_profit_usd=by_id[pa_id].equity_profit_usd,
            entry_peak_profit_usd=by_id[pa_id].peak_profit_usd,
            entry_floor_profit_usd=by_id[pa_id].liquidation_floor_profit_usd,
        )
        for pa_id in eligible
    )
    recorded_blocks = tuple(
        (pa_id, blocks[pa_id]) for pa_id in candidates if pa_id in blocks
    )
    return CopyDecision(
        opportunity=opportunity,
        scaling_policy_id=scaling.policy_id,
        candidate_pa_ids=tuple(candidates),
        eligible_pa_ids=tuple(eligible),
        compliance_blocks=recorded_blocks,
        copies=copies,
    )


def _breached(value: float, floor: float, *, touch_fails: bool) -> bool:
    return value <= floor if touch_fails else value < floor


def _lift_peak(
    account: PAAccount,
    value: float,
    *,
    trailing_drawdown_usd: float,
    frozen_floor_profit_usd: float,
) -> None:
    account.peak_profit_usd = money(max(account.peak_profit_usd, value))
    account.liquidation_floor_profit_usd = money(
        min(
            account.peak_profit_usd - trailing_drawdown_usd,
            frozen_floor_profit_usd,
        )
    )


def settle_account_copy(
    account: PAAccount,
    offer: TradeOffer,
    copy: AccountCopy,
    *,
    event_at: datetime,
    path_order: SettlementPathOrder,
    commission_timing: CommissionTiming,
    trailing_drawdown_usd: float = 1_500.0,
    frozen_floor_profit_usd: float = 100.0,
    threshold_touch_fails: bool = True,
    execution: ExecutionModel = FRICTIONLESS,
) -> PATradeResult:
    """Apply linear per-MNQ completed-trade outcomes to one copied account."""

    if event_at.tzinfo is None or event_at != offer.exit_at:
        raise ValueError("Completed-trade settlement must occur at the exact exit event")
    if copy.pa_id != account.pa_id:
        raise ValueError("Copy PA ID does not match account")
    if not account.alive:
        raise ValueError("Cannot settle a copy on a dead PA")
    if not account.activated_at < offer.entry_at:
        raise ValueError("PA activation must be strictly earlier than trade entry")
    _assert_copy_entry_state(account, copy)
    if path_order == "resolved":
        path_order = offer.resolved_path_order
    if path_order not in {"mae_first", "mfe_first"}:
        raise ValueError("Unsupported PA intratrade path order")
    if commission_timing not in {"close_only", "intratrade_and_close"}:
        raise ValueError("Unsupported PA commission timing")
    if (
        not math.isfinite(trailing_drawdown_usd)
        or trailing_drawdown_usd <= 0
        or not math.isfinite(frozen_floor_profit_usd)
        or not isinstance(threshold_touch_fails, bool)
    ):
        raise ValueError("PA drawdown settlement inputs are invalid")

    before_equity = account.equity_profit_usd
    before_floor = account.liquidation_floor_profit_usd
    contracts = copy.mnq
    commission = money(contracts * offer.commission_usd_per_mnq)
    intratrade_commission = (
        commission if commission_timing == "intratrade_and_close" else 0.0
    )
    # Entry-side slippage is already paid while the position is open, so it
    # lowers the modelled excursion and can itself cause an intratrade death.
    entry_slippage = money(contracts * execution.slippage_usd_per_mnq_per_side)
    round_turn_slippage = money(contracts * execution.slippage_usd_per_mnq_round_turn)
    adverse = money(
        account.equity_profit_usd
        + contracts * min(offer.mae_usd_per_mnq, 0.0)
        - intratrade_commission
        - entry_slippage
    )
    favorable = money(
        account.equity_profit_usd
        + contracts * max(offer.mfe_usd_per_mnq, 0.0)
        - intratrade_commission
        - entry_slippage
    )
    net_pnl = money(
        contracts * offer.gross_pnl_usd_per_mnq - commission - round_turn_slippage
    )
    closing = money(account.equity_profit_usd + net_pnl)
    account.last_mnq = contracts

    if path_order == "mfe_first":
        _lift_peak(
            account,
            favorable,
            trailing_drawdown_usd=trailing_drawdown_usd,
            frozen_floor_profit_usd=frozen_floor_profit_usd,
        )
    if _breached(
        adverse,
        account.liquidation_floor_profit_usd,
        touch_fails=threshold_touch_fails,
    ):
        account.alive = False
        return PATradeResult(
            event_at=event_at,
            pa_id=account.pa_id,
            trade_key=offer.trade_key,
            mnq=contracts,
            survived=False,
            death_reason="intratrade_drawdown",
            completed_trade_outcome_applied=False,
            net_pnl_usd=None,
            commission_usd=None,
            path_order=path_order,
            commission_timing=commission_timing,
            equity_before_usd=before_equity,
            equity_after_usd=account.equity_profit_usd,
            floor_before_usd=before_floor,
            floor_after_usd=account.liquidation_floor_profit_usd,
        )
    if path_order == "mae_first":
        _lift_peak(
            account,
            favorable,
            trailing_drawdown_usd=trailing_drawdown_usd,
            frozen_floor_profit_usd=frozen_floor_profit_usd,
        )

    account.equity_profit_usd = closing
    _lift_peak(
        account,
        closing,
        trailing_drawdown_usd=trailing_drawdown_usd,
        frozen_floor_profit_usd=frozen_floor_profit_usd,
    )
    account.completed_count += 1
    day = offer.exit_trading_day
    account.realized_daily_pnl_usd[day] = money(
        account.realized_daily_pnl_usd.get(day, 0.0) + net_pnl
    )
    account.payout_period_daily_pnl_usd[day] = money(
        account.payout_period_daily_pnl_usd.get(day, 0.0) + net_pnl
    )
    if _breached(
        account.equity_profit_usd,
        account.liquidation_floor_profit_usd,
        touch_fails=threshold_touch_fails,
    ):
        account.alive = False
        death_reason = "closing_drawdown"
    else:
        death_reason = None

    return PATradeResult(
        event_at=event_at,
        pa_id=account.pa_id,
        trade_key=offer.trade_key,
        mnq=contracts,
        survived=account.alive,
        death_reason=death_reason,
        completed_trade_outcome_applied=True,
        net_pnl_usd=net_pnl,
        commission_usd=commission,
        path_order=path_order,
        commission_timing=commission_timing,
        equity_before_usd=before_equity,
        equity_after_usd=account.equity_profit_usd,
        floor_before_usd=before_floor,
        floor_after_usd=account.liquidation_floor_profit_usd,
    )


def settle_copy_decision(
    decision: CopyDecision,
    accounts_by_id: Mapping[int, PAAccount],
    *,
    event_at: datetime,
    path_order: SettlementPathOrder,
    commission_timing: CommissionTiming,
    execution: ExecutionModel = FRICTIONLESS,
) -> tuple[PATradeResult, ...]:
    if decision.settled_at is not None:
        raise ValueError("Copy decision has already been settled")
    offer = decision.opportunity.offer
    if event_at.tzinfo is None or event_at != decision.exit_at:
        raise ValueError("Copy decision must settle at its exact exit event")
    if path_order not in {"resolved", "mae_first", "mfe_first"}:
        raise ValueError("Unsupported PA intratrade path order")
    if commission_timing not in {"close_only", "intratrade_and_close"}:
        raise ValueError("Unsupported PA commission timing")
    missing = set(decision.eligible_pa_ids) - set(accounts_by_id)
    if missing:
        raise ValueError(f"Missing PA state for copied accounts: {sorted(missing)}")
    for copy in decision.copies:
        account = accounts_by_id[copy.pa_id]
        if (
            account.pa_id != copy.pa_id
            or not account.alive
            or not account.activated_at < offer.entry_at
        ):
            raise ValueError("Copied PA is no longer valid for deterministic settlement")
        _assert_copy_entry_state(account, copy)
    decision.settled_at = event_at
    return tuple(
        settle_account_copy(
            accounts_by_id[copy.pa_id],
            offer,
            copy,
            event_at=event_at,
            path_order=path_order,
            commission_timing=commission_timing,
            execution=execution,
        )
        for copy in decision.copies
    )
