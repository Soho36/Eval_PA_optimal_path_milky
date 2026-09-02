"""Explicit Legacy 25K PA payout rules and candidate-policy execution.

Implementation provenance:
- reviewed parent repository at revision
  106cfb782c6e573856282095441bb69f23924a55
- reference/shared_source/rules.py SHA-256
  f3924f349ef88f0b79803d001cb37e790c19624b243f07ffdd7525a7c6c68253
- reference/shared_source/payouts.py SHA-256
  1448447c39b89490ceab4524eb5d755a8a33dca10818910274d26f3be8c6c2e6

This is a narrow selective adaptation for independent copy-to-all PAs. Payout
timing is supplied explicitly by the caller; no study-wide timing policy is
selected here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any, Literal

from .copy_to_all import PAAccount
from .inputs import money


PayoutRuleKind = Literal["minimum", "maximum", "fixed", "fraction"]
BASELINE_POLICY_IDS = {
    "minimum_500_always",
    "maximum_always",
    "rush_to_uncapped",
    "cap_maximizer",
    "preserve_safety_net",
    "half_of_maximum",
}


@dataclass(frozen=True, slots=True)
class Legacy25KPayoutRules:
    nominal_balance_usd: float = 25_000.0
    minimum_days: int = 8
    minimum_profitable_days: int = 5
    profitable_day_usd: float = 50.0
    request_gate_balance_usd: float = 26_600.0
    safety_net_balance_usd: float = 26_600.0
    minimum_request_usd: float = 500.0
    first_five_cap_usd: float = 1_500.0
    safety_net_request_count: int = 3
    capped_request_count: int = 5
    post_safety_minimum_balance_usd: float = 25_100.01
    full_split_cumulative_usd: float = 25_000.0
    split_after_full: float = 0.90

    def __post_init__(self) -> None:
        numeric = (
            self.nominal_balance_usd,
            self.profitable_day_usd,
            self.request_gate_balance_usd,
            self.safety_net_balance_usd,
            self.minimum_request_usd,
            self.first_five_cap_usd,
            self.post_safety_minimum_balance_usd,
            self.full_split_cumulative_usd,
            self.split_after_full,
        )
        if not all(math.isfinite(value) and value > 0 for value in numeric):
            raise ValueError("Payout-rule monetary values must be finite and positive")
        counts = (
            self.minimum_days,
            self.minimum_profitable_days,
            self.safety_net_request_count,
            self.capped_request_count,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in counts
        ):
            raise ValueError("Payout-rule counts must be positive integers")
        if self.minimum_profitable_days > self.minimum_days:
            raise ValueError("Profitable-day minimum cannot exceed the day minimum")
        if self.minimum_request_usd > self.first_five_cap_usd:
            raise ValueError("Payout minimum cannot exceed the capped maximum")
        if self.safety_net_request_count > self.capped_request_count:
            raise ValueError("Safety-net count cannot exceed the capped count")
        if not 0 < self.split_after_full <= 1:
            raise ValueError("Post-threshold payout split must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class PayoutRule:
    kind: PayoutRuleKind
    amount_usd: float | None = None
    fraction: float | None = None
    require_full: bool = True

    def __post_init__(self) -> None:
        if self.kind == "fixed":
            if (
                self.amount_usd is None
                or not math.isfinite(self.amount_usd)
                or self.amount_usd <= 0
                or self.fraction is not None
            ):
                raise ValueError("Fixed payout rule requires only a positive amount")
        elif self.kind == "fraction":
            if (
                self.fraction is None
                or not math.isfinite(self.fraction)
                or not 0 < self.fraction <= 1
                or self.amount_usd is not None
            ):
                raise ValueError("Fraction payout rule requires only a fraction in (0, 1]")
        elif self.kind in {"minimum", "maximum"}:
            if self.amount_usd is not None or self.fraction is not None:
                raise ValueError(f"{self.kind} payout rule takes no amount or fraction")
        else:
            raise ValueError(f"Unsupported payout rule kind: {self.kind}")
        if not isinstance(self.require_full, bool):
            raise ValueError("Payout require_full flag must be boolean")


@dataclass(frozen=True, slots=True)
class PayoutPolicy:
    policy_id: str
    early_rule: PayoutRule
    switch_after_payout_number: int | None = None
    late_rule: PayoutRule | None = None
    post_payout_floor_balance_usd: float | None = None

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("Payout policy_id is required")
        if not isinstance(self.early_rule, PayoutRule) or (
            self.late_rule is not None and not isinstance(self.late_rule, PayoutRule)
        ):
            raise ValueError("Payout policy rules must be PayoutRule instances")
        if (self.late_rule is None) != (self.switch_after_payout_number is None):
            raise ValueError("Payout switch and late rule must be supplied together")
        if self.switch_after_payout_number is not None and (
            not isinstance(self.switch_after_payout_number, int)
            or isinstance(self.switch_after_payout_number, bool)
            or self.switch_after_payout_number <= 0
        ):
            raise ValueError("Payout switch number must be a positive integer")
        if self.post_payout_floor_balance_usd is not None and (
            not math.isfinite(self.post_payout_floor_balance_usd)
            or self.post_payout_floor_balance_usd <= 0
        ):
            raise ValueError("Payout policy balance floor must be finite and positive")

    def rule_for(self, executed_payouts: int) -> PayoutRule:
        if (
            self.late_rule is not None
            and self.switch_after_payout_number is not None
            and executed_payouts >= self.switch_after_payout_number
        ):
            return self.late_rule
        return self.early_rule


@dataclass(frozen=True, slots=True)
class PayoutRecord:
    event_at: datetime
    pa_id: int
    payout_number: int
    policy_id: str
    gross_request_usd: float
    treasury_receipt_usd: float
    balance_before_usd: float
    balance_after_usd: float
    trading_days_in_period: int
    profitable_days_in_period: int
    lifecycle_timing: Literal["atomic_pa_debit_and_treasury_receipt"] = (
        "atomic_pa_debit_and_treasury_receipt"
    )

    def __post_init__(self) -> None:
        if self.event_at.tzinfo is None:
            raise ValueError("Payout-record timestamp must be timezone-aware")
        for name, value in (
            ("PA ID", self.pa_id),
            ("payout number", self.payout_number),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"Payout-record {name} must be a positive integer")
        if not self.policy_id:
            raise ValueError("Payout record requires a policy identity")
        monetary = (
            self.gross_request_usd,
            self.treasury_receipt_usd,
            self.balance_before_usd,
            self.balance_after_usd,
        )
        if not all(math.isfinite(value) for value in monetary):
            raise ValueError("Payout-record monetary values must be finite")
        if self.gross_request_usd <= 0:
            raise ValueError("Payout-record gross request must be positive")
        if not 0 <= self.treasury_receipt_usd <= self.gross_request_usd:
            raise ValueError("Payout receipt must be between zero and gross request")
        if self.balance_after_usd != money(
            self.balance_before_usd - self.gross_request_usd
        ):
            raise ValueError("Payout-record balances do not reconcile to gross request")
        for name, value in (
            ("trading-day count", self.trading_days_in_period),
            ("profitable-day count", self.profitable_days_in_period),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"Payout-record {name} must be a non-negative integer")
        if self.profitable_days_in_period > self.trading_days_in_period:
            raise ValueError("Profitable payout days cannot exceed trading days")
        if self.lifecycle_timing != "atomic_pa_debit_and_treasury_receipt":
            raise ValueError("Unsupported payout-record lifecycle timing")


def _floor_cents(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("Payout amount must be finite")
    return math.floor((value + 1e-9) * 100) / 100


def maximum_eligible_gross(
    account: PAAccount,
    rules: Legacy25KPayoutRules = Legacy25KPayoutRules(),
) -> float:
    """Return the rule ceiling before a candidate policy chooses an amount."""

    if not account.alive:
        return 0.0
    balance = account.nominal_balance_usd
    if balance < rules.request_gate_balance_usd:
        return 0.0
    payout_number = account.payout_count + 1
    if payout_number <= rules.safety_net_request_count:
        available = rules.minimum_request_usd + max(
            0.0,
            balance - rules.safety_net_balance_usd,
        )
    else:
        available = max(0.0, balance - rules.post_safety_minimum_balance_usd)
    if payout_number <= rules.capped_request_count:
        available = min(available, rules.first_five_cap_usd)
    return _floor_cents(max(0.0, available))


def payout_period_counts(
    account: PAAccount,
    rules: Legacy25KPayoutRules = Legacy25KPayoutRules(),
) -> tuple[int, int]:
    history = account.payout_period_daily_pnl_usd
    return (
        len(history),
        sum(value >= rules.profitable_day_usd for value in history.values()),
    )


def choose_payout_amount(
    account: PAAccount,
    policy: PayoutPolicy,
    rules: Legacy25KPayoutRules = Legacy25KPayoutRules(),
) -> float | None:
    days, profitable_days = payout_period_counts(account, rules)
    if days < rules.minimum_days or profitable_days < rules.minimum_profitable_days:
        return None
    maximum = maximum_eligible_gross(account, rules)
    if policy.post_payout_floor_balance_usd is not None:
        maximum = min(
            maximum,
            _floor_cents(
                max(
                    0.0,
                    account.nominal_balance_usd
                    - policy.post_payout_floor_balance_usd,
                )
            ),
        )
    if maximum < rules.minimum_request_usd:
        return None

    selected = policy.rule_for(account.payout_count)
    if selected.kind == "minimum":
        desired = rules.minimum_request_usd
    elif selected.kind == "maximum":
        desired = maximum
    elif selected.kind == "fixed":
        assert selected.amount_usd is not None
        if selected.amount_usd > maximum and selected.require_full:
            return None
        desired = min(selected.amount_usd, maximum)
    else:
        assert selected.kind == "fraction" and selected.fraction is not None
        desired = _floor_cents(maximum * selected.fraction)
    amount = max(rules.minimum_request_usd, min(_floor_cents(desired), maximum))
    return money(amount) if amount >= rules.minimum_request_usd else None


def execute_atomic_payout_if_eligible(
    account: PAAccount,
    event_at: datetime,
    policy: PayoutPolicy,
    rules: Legacy25KPayoutRules = Legacy25KPayoutRules(),
) -> PayoutRecord | None:
    """Atomically debit one eligible PA and return its treasury receipt record."""

    if event_at.tzinfo is None:
        raise ValueError("Payout event must be timezone-aware")
    if event_at < account.activated_at:
        raise ValueError("Payout cannot precede PA activation")
    amount = choose_payout_amount(account, policy, rules)
    if amount is None:
        return None
    days, profitable_days = payout_period_counts(account, rules)
    before = account.nominal_balance_usd
    equity_after = money(account.equity_profit_usd - amount)
    if equity_after <= account.liquidation_floor_profit_usd:
        raise RuntimeError("Payout execution would breach the PA liquidation floor")
    remaining_full_split = max(
        0.0,
        rules.full_split_cumulative_usd - account.cumulative_gross_payouts_usd,
    )
    full_split = min(amount, remaining_full_split)
    reduced_split = amount - full_split
    receipt = money(full_split + reduced_split * rules.split_after_full)

    payout_count_after = account.payout_count + 1
    cumulative_gross_after = money(account.cumulative_gross_payouts_usd + amount)
    cumulative_net_after = money(account.cumulative_net_payouts_usd + receipt)
    balance_after = money(before - amount)
    postcondition_money = (
        equity_after,
        receipt,
        cumulative_gross_after,
        cumulative_net_after,
        balance_after,
    )
    if not all(math.isfinite(value) for value in postcondition_money):
        raise ValueError("Payout postcondition monetary values must be finite")
    if receipt < 0 or receipt > amount:
        raise ValueError("Payout receipt must be between zero and gross request")
    if cumulative_gross_after < 0 or cumulative_net_after < 0:
        raise ValueError("Cumulative payout postconditions must be non-negative")
    if cumulative_net_after > cumulative_gross_after:
        raise ValueError("Cumulative net payouts cannot exceed cumulative gross payouts")

    # Construct and validate the complete result before touching mutable PA
    # state. If any calculation or record postcondition fails, the account is
    # therefore unchanged without relying on a caller-owned rollback.
    record = PayoutRecord(
        event_at=event_at,
        pa_id=account.pa_id,
        payout_number=payout_count_after,
        policy_id=policy.policy_id,
        gross_request_usd=amount,
        treasury_receipt_usd=receipt,
        balance_before_usd=before,
        balance_after_usd=balance_after,
        trading_days_in_period=days,
        profitable_days_in_period=profitable_days,
    )

    account.equity_profit_usd = equity_after
    account.payout_count = payout_count_after
    account.cumulative_gross_payouts_usd = cumulative_gross_after
    account.cumulative_net_payouts_usd = cumulative_net_after
    account.payout_period_daily_pnl_usd = {}
    return record


def _payout_rule(payload: dict[str, Any]) -> PayoutRule:
    known = {"kind", "amount_usd", "fraction", "require_full"}
    unknown = set(payload) - known
    if unknown:
        raise ValueError(f"Unknown payout-rule fields: {sorted(unknown)}")
    return PayoutRule(
        kind=payload["kind"],
        amount_usd=payload.get("amount_usd"),
        fraction=payload.get("fraction"),
        require_full=payload.get("require_full", True),
    )


def load_payout_policies(path: str | Path) -> tuple[PayoutPolicy, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise ValueError("Unsupported payout-policy schema version")
    if payload.get("schema_id") != "legacy_25k_payout_policies.v2":
        raise ValueError("Unsupported payout-policy schema identity")
    common = payload.get("common_execution", {})
    expected_common = {
        "only_request_when_baseline_eligibility_is_true": True,
        "apply_eligible_balance_amount_and_payout_number_cap": True,
        "minimum_gross_request_usd": 500,
        "fixed_amount_rule_with_require_full_waits_for_the_whole_amount": True,
        "round_gross_request_down_to_cents": True,
        "request_approval_and_receipt_are_atomic": True,
        "denials_and_delays_modeled": False,
    }
    if common != expected_common:
        raise ValueError("Candidate payout file has incompatible execution declarations")
    policies: list[PayoutPolicy] = []
    known = {
        "policy_id",
        "label",
        "description",
        "early_rule",
        "switch_after_payout_number",
        "late_rule",
        "post_payout_floor_balance_usd",
    }
    for row in payload.get("policies", []):
        unknown = set(row) - known
        if unknown:
            raise ValueError(f"Unknown payout-policy fields: {sorted(unknown)}")
        late = row.get("late_rule")
        policies.append(
            PayoutPolicy(
                policy_id=row["policy_id"],
                early_rule=_payout_rule(row["early_rule"]),
                switch_after_payout_number=row.get("switch_after_payout_number"),
                late_rule=_payout_rule(late) if late is not None else None,
                post_payout_floor_balance_usd=row.get(
                    "post_payout_floor_balance_usd"
                ),
            )
        )
    ids = [policy.policy_id for policy in policies]
    if len(ids) != len(set(ids)) or set(ids) != BASELINE_POLICY_IDS:
        raise ValueError("Candidate payout-policy identities do not match the required six")
    return tuple(policies)
