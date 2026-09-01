"""Cash ledger and explicit external-capital authorization contracts.

Implementation provenance:
- reviewed parent treasury mechanics at revision
  106cfb782c6e573856282095441bb69f23924a55
- reference/shared_source/treasury.py SHA-256
  c6f29e2294c66c7b1321dc9a581b37f76410044f74250ce349c2c570e76c79a9

This selective adaptation adds explicit policy validation, starting cash, and
an irreversible first-PA activation latch. It does not select a capital policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Literal


CapitalMode = Literal["none", "fixed_budget", "through_first_pa"]
FeePurpose = Literal[
    "evaluation_purchase", "evaluation_renewal", "pa_activation"
]
_FEE_PURPOSES = {"evaluation_purchase", "evaluation_renewal", "pa_activation"}


def money(value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Money values must be finite")
    return round(number, 2)


@dataclass(frozen=True, slots=True)
class ExternalCapitalPolicy:
    policy_id: str
    mode: CapitalMode
    permitted_uses: tuple[FeePurpose, ...]
    lifetime_cap_usd: float | None
    contribution_timing: Literal["just_in_time_exact_shortfall"]
    close_event: Literal["never", "first_pa_activated"]
    reopens: bool

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("External-capital policy_id is required")
        if self.mode not in {"none", "fixed_budget", "through_first_pa"}:
            raise ValueError("Unsupported external-capital mode")
        if self.contribution_timing != "just_in_time_exact_shortfall":
            raise ValueError("Unsupported external-capital contribution timing")
        if self.close_event not in {"never", "first_pa_activated"}:
            raise ValueError("Unsupported external-capital close event")
        if len(self.permitted_uses) != len(set(self.permitted_uses)):
            raise ValueError("External-capital permitted uses must be unique")
        if any(purpose not in _FEE_PURPOSES for purpose in self.permitted_uses):
            raise ValueError("Unsupported external-capital permitted use")
        if self.lifetime_cap_usd is not None:
            if not math.isfinite(self.lifetime_cap_usd):
                raise ValueError("External-capital cap must be finite")
            if self.lifetime_cap_usd < 0:
                raise ValueError("External-capital cap cannot be negative")
        if self.mode == "none":
            if self.permitted_uses or self.lifetime_cap_usd not in {None, 0}:
                raise ValueError("No-capital mode cannot authorize uses or a budget")
            if self.close_event != "never":
                raise ValueError("No-capital mode has no bridge-closing event")
        elif not self.permitted_uses:
            raise ValueError("Capital policy must name permitted uses")
        if self.mode == "fixed_budget":
            if self.lifetime_cap_usd is None:
                raise ValueError("fixed_budget requires a non-negative lifetime cap")
            if self.close_event != "never":
                raise ValueError("fixed_budget closes only through budget exhaustion")
        if self.mode == "through_first_pa" and self.close_event != "first_pa_activated":
            raise ValueError("through_first_pa must close at first PA activation")
        if self.reopens:
            raise ValueError("External-capital bridges may not silently reopen")

    def authorizes(
        self,
        purpose: FeePurpose,
        *,
        bridge_closed: bool,
        contributed_usd: float,
        shortfall_usd: float,
    ) -> bool:
        if any(
            not math.isfinite(value) or value < 0
            for value in (contributed_usd, shortfall_usd)
        ):
            raise ValueError("Capital authorization amounts must be finite and non-negative")
        if shortfall_usd == 0:
            return True
        if self.mode == "none" or purpose not in self.permitted_uses:
            return False
        if self.close_event == "first_pa_activated" and bridge_closed:
            return False
        if self.lifetime_cap_usd is None:
            return True
        return contributed_usd + shortfall_usd <= self.lifetime_cap_usd + 1e-9


@dataclass(frozen=True, slots=True)
class CashLedgerEntry:
    event_at: datetime
    kind: str
    amount_usd: float
    purpose: str
    reference: str
    cash_after_usd: float


@dataclass(slots=True)
class Treasury:
    starting_cash_usd: float = 0.0
    cash_usd: float = field(init=False)
    external_contributions_usd: float = field(init=False, default=0.0)
    payout_receipts_usd: float = field(init=False, default=0.0)
    fees_paid_usd: float = field(init=False, default=0.0)
    first_pa_activated_at: datetime | None = field(init=False, default=None)
    ledger: list[CashLedgerEntry] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.starting_cash_usd = money(self.starting_cash_usd)
        if self.starting_cash_usd < 0:
            raise ValueError("Starting treasury cash cannot be negative")
        self.cash_usd = self.starting_cash_usd

    def _append(
        self,
        event_at: datetime,
        kind: str,
        amount_usd: float,
        purpose: str,
        reference: str,
    ) -> None:
        if event_at.tzinfo is None:
            raise ValueError("Cash events must be timezone-aware")
        if not purpose or not reference:
            raise ValueError("Cash events require purpose and reference")
        if self.ledger and event_at < self.ledger[-1].event_at:
            raise ValueError("Cash events must be chronological")
        if self.first_pa_activated_at is not None and event_at < self.first_pa_activated_at:
            raise ValueError("Cash event precedes the recorded first PA activation")
        self.cash_usd = money(self.cash_usd + amount_usd)
        self.ledger.append(
            CashLedgerEntry(
                event_at=event_at,
                kind=kind,
                amount_usd=money(amount_usd),
                purpose=purpose,
                reference=reference,
                cash_after_usd=self.cash_usd,
            )
        )

    @property
    def external_bridge_closed(self) -> bool:
        return self.first_pa_activated_at is not None

    def observe_first_pa_activation(self, event_at: datetime) -> None:
        if event_at.tzinfo is None:
            raise ValueError("PA activation timestamp must be timezone-aware")
        if self.ledger and event_at < self.ledger[-1].event_at:
            raise ValueError("First PA activation cannot precede recorded cash events")
        if self.first_pa_activated_at is None:
            self.first_pa_activated_at = event_at
        elif self.first_pa_activated_at != event_at:
            raise ValueError("First PA activation timestamp is immutable")

    def receive_payout(
        self, event_at: datetime, amount_usd: float, reference: str
    ) -> None:
        amount = money(amount_usd)
        if amount <= 0:
            raise ValueError("Payout receipt must be positive")
        self._append(event_at, "payout_receipt", amount, "payout", reference)
        self.payout_receipts_usd = money(self.payout_receipts_usd + amount)

    def fund_and_pay_fee(
        self,
        event_at: datetime,
        amount_usd: float,
        purpose: FeePurpose,
        reference: str,
        capital_policy: ExternalCapitalPolicy,
    ) -> bool:
        """Pay atomically, contributing exactly the full shortfall or nothing."""

        if purpose not in _FEE_PURPOSES:
            raise ValueError("Unsupported lifecycle fee purpose")
        amount = money(amount_usd)
        if amount <= 0:
            raise ValueError("Fee must be positive")
        shortfall = money(max(0.0, amount - self.cash_usd))
        if shortfall and not capital_policy.authorizes(
            purpose,
            bridge_closed=self.external_bridge_closed,
            contributed_usd=self.external_contributions_usd,
            shortfall_usd=shortfall,
        ):
            return False
        if shortfall:
            self._append(
                event_at,
                "external_contribution",
                shortfall,
                purpose,
                f"{reference}:external_shortfall",
            )
            self.external_contributions_usd = money(
                self.external_contributions_usd + shortfall
            )
        self._append(event_at, "fee", -amount, purpose, reference)
        self.fees_paid_usd = money(self.fees_paid_usd + amount)
        return True

    @property
    def reconciliation_error_usd(self) -> float:
        expected = money(
            self.starting_cash_usd
            + self.external_contributions_usd
            + self.payout_receipts_usd
            - self.fees_paid_usd
        )
        return money(self.cash_usd - expected)

    def assert_integrity(self) -> None:
        cash = self.starting_cash_usd
        external = payouts = fees = 0.0
        previous: datetime | None = None
        for index, entry in enumerate(self.ledger, start=1):
            if previous is not None and entry.event_at < previous:
                raise RuntimeError(f"Cash ledger row {index} is not chronological")
            previous = entry.event_at
            cash = money(cash + entry.amount_usd)
            if cash != entry.cash_after_usd:
                raise RuntimeError(f"Cash ledger row {index} balance mismatch")
            if entry.kind == "external_contribution":
                if entry.amount_usd <= 0:
                    raise RuntimeError("External contribution must be positive")
                external = money(external + entry.amount_usd)
            elif entry.kind == "payout_receipt":
                if entry.amount_usd <= 0:
                    raise RuntimeError("Payout receipt must be positive")
                payouts = money(payouts + entry.amount_usd)
            elif entry.kind == "fee":
                if entry.amount_usd >= 0:
                    raise RuntimeError("Fee must be negative")
                fees = money(fees - entry.amount_usd)
            else:
                raise RuntimeError(f"Unsupported cash ledger kind: {entry.kind}")
        observed = (cash, external, payouts, fees)
        expected = (
            self.cash_usd,
            self.external_contributions_usd,
            self.payout_receipts_usd,
            self.fees_paid_usd,
        )
        if observed != expected or self.reconciliation_error_usd != 0:
            raise RuntimeError(
                f"Cash ledger reconciliation mismatch: {observed} != {expected}"
            )
