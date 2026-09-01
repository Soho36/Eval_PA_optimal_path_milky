"""Simplified, immediately received Legacy 25K payout policy comparison."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from .models import money
from .pa import PAState
from .rules import Legacy25KRules, PayoutPolicy


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


def _floor_cents(value: float) -> float:
    return math.floor((value + 1e-9) * 100) / 100


def maximum_eligible_gross(pa: PAState, rules: Legacy25KRules) -> float:
    """Return the study-baseline request ceiling before a policy chooses an amount."""

    number = pa.payout_count + 1
    balance = rules.nominal_balance_usd + pa.equity_profit_usd
    if balance < rules.payout_request_gate_balance_usd:
        return 0.0
    if number <= rules.payout_safety_net_request_count:
        # The supplied first-three rule permits the minimum $500 at the safety
        # balance, then requires one extra balance dollar per extra request dollar.
        available = rules.payout_minimum_request_usd + max(
            0.0, balance - rules.payout_safety_net_balance_usd
        )
    else:
        available = max(0.0, balance - rules.payout_post_safety_minimum_balance_usd)
    if number <= rules.payout_cap_request_count:
        available = min(available, rules.payout_first_five_cap_usd)
    return _floor_cents(max(0.0, available))


def choose_payout_amount(
    pa: PAState, rules: Legacy25KRules, policy: PayoutPolicy
) -> float | None:
    """Return the gross request this policy makes now, or None to wait.

    Baseline eligibility is checked first and is common to every policy. Only
    then does the policy choose an amount inside the eligible range.
    """

    days = len(pa.payout_period_daily_pnl)
    profitable = sum(
        pnl >= rules.payout_profitable_day_usd
        for pnl in pa.payout_period_daily_pnl.values()
    )
    if days < rules.payout_minimum_days or profitable < rules.payout_minimum_profitable_days:
        return None
    if policy.accumulated_profit_trigger_usd is not None:
        if pa.accumulated_profit_bank_usd < policy.accumulated_profit_trigger_usd:
            return None

    maximum = maximum_eligible_gross(pa, rules)
    if policy.post_payout_floor_balance_usd is not None:
        balance = rules.nominal_balance_usd + pa.equity_profit_usd
        maximum = min(
            maximum,
            _floor_cents(max(0.0, balance - policy.post_payout_floor_balance_usd)),
        )
    if maximum < rules.payout_minimum_request_usd:
        return None

    rule = policy.rule_for(pa.payout_count)
    if rule.kind == "minimum":
        desired = rules.payout_minimum_request_usd
    elif rule.kind == "maximum":
        desired = maximum
    elif rule.kind == "fixed":
        assert rule.amount_usd is not None
        desired = rule.amount_usd
        if desired > maximum:
            # require_full waits for the whole amount to become eligible rather
            # than silently degrading into a different, smaller policy.
            return None if rule.require_full else maximum
    elif rule.kind == "fraction":
        assert rule.fraction is not None
        desired = _floor_cents(maximum * rule.fraction)
    else:  # pragma: no cover - guarded by PayoutRule validation
        raise ValueError(f"Unsupported payout rule kind: {rule.kind}")

    amount = max(rules.payout_minimum_request_usd, min(money(desired), maximum))
    return money(amount) if amount >= rules.payout_minimum_request_usd else None


def _trader_receipt(pa: PAState, gross: float, rules: Legacy25KRules) -> float:
    remaining_full = max(
        0.0,
        rules.payout_full_split_cumulative_usd - pa.cumulative_gross_payouts_usd,
    )
    full = min(gross, remaining_full)
    split = gross - full
    return money(full + split * rules.payout_split_after_full)


def execute_payout(
    pa: PAState,
    event_at: datetime,
    amount_usd: float,
    rules: Legacy25KRules,
    policy: PayoutPolicy,
) -> PayoutRecord:
    amount = money(amount_usd)
    if amount < rules.payout_minimum_request_usd:
        raise ValueError("Payout is below the configured minimum")
    if amount > maximum_eligible_gross(pa, rules):
        raise ValueError("Payout exceeds the eligible maximum")
    if policy.post_payout_floor_balance_usd is not None:
        remaining = money(
            rules.nominal_balance_usd + pa.equity_profit_usd - amount
        )
        if remaining < policy.post_payout_floor_balance_usd:
            raise ValueError("Payout breaches the policy post-payout balance floor")
    before = money(rules.nominal_balance_usd + pa.equity_profit_usd)
    receipt = _trader_receipt(pa, amount, rules)
    pa.equity_profit_usd = money(pa.equity_profit_usd - amount)
    pa.payout_count += 1
    pa.cumulative_gross_payouts_usd = money(
        pa.cumulative_gross_payouts_usd + amount
    )
    pa.cumulative_net_payouts_usd = money(
        pa.cumulative_net_payouts_usd + receipt
    )
    if policy.accumulated_profit_trigger_usd is not None:
        pa.accumulated_profit_bank_usd = money(
            pa.accumulated_profit_bank_usd - policy.accumulated_profit_trigger_usd
        )
    pa.payout_period_daily_pnl.clear()
    after = money(rules.nominal_balance_usd + pa.equity_profit_usd)
    return PayoutRecord(
        event_at=event_at,
        pa_id=pa.pa_id,
        payout_number=pa.payout_count,
        policy_id=policy.policy_id,
        gross_request_usd=amount,
        treasury_receipt_usd=receipt,
        balance_before_usd=before,
        balance_after_usd=after,
    )
