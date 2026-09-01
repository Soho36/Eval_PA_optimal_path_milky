"""Double-count-free external cash ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import CashLedgerEntry, money


@dataclass(slots=True)
class Treasury:
    cash_usd: float = 0.0
    external_contributions_usd: float = 0.0
    payout_receipts_usd: float = 0.0
    evaluation_fees_usd: float = 0.0
    activation_fees_usd: float = 0.0
    ledger: list[CashLedgerEntry] = field(default_factory=list)

    def contribute(self, event_at: datetime, amount_usd: float, reference: str) -> None:
        amount = money(amount_usd)
        if amount <= 0:
            raise ValueError("Contribution must be positive")
        self.cash_usd = money(self.cash_usd + amount)
        self.external_contributions_usd = money(
            self.external_contributions_usd + amount
        )
        self.ledger.append(
            CashLedgerEntry(event_at, "external_contribution", amount, reference, self.cash_usd)
        )

    def receive_payout(self, event_at: datetime, amount_usd: float, reference: str) -> None:
        amount = money(amount_usd)
        if amount <= 0:
            raise ValueError("Payout receipt must be positive")
        self.cash_usd = money(self.cash_usd + amount)
        self.payout_receipts_usd = money(self.payout_receipts_usd + amount)
        self.ledger.append(CashLedgerEntry(event_at, "payout", amount, reference, self.cash_usd))

    def spend_fee(
        self, event_at: datetime, amount_usd: float, kind: str, reference: str
    ) -> bool:
        amount = money(amount_usd)
        if kind not in {"evaluation_fee", "activation_fee"}:
            raise ValueError(f"Unsupported fee kind: {kind}")
        if amount <= 0:
            raise ValueError("Fee must be positive")
        if self.cash_usd + 1e-9 < amount:
            return False
        self.cash_usd = money(self.cash_usd - amount)
        if kind == "evaluation_fee":
            self.evaluation_fees_usd = money(self.evaluation_fees_usd + amount)
        else:
            self.activation_fees_usd = money(self.activation_fees_usd + amount)
        self.ledger.append(CashLedgerEntry(event_at, kind, -amount, reference, self.cash_usd))
        return True

    def assert_ledger_integrity(self) -> None:
        """Rebuild every balance and category total from immutable ledger rows."""

        cash = external = payouts = evaluation_fees = activation_fees = 0.0
        previous_at: datetime | None = None
        for index, entry in enumerate(self.ledger, start=1):
            if previous_at is not None and entry.event_at < previous_at:
                raise RuntimeError(f"Cash ledger row {index} is not chronological")
            if not entry.reference:
                raise RuntimeError(f"Cash ledger row {index} has no reference")
            previous_at = entry.event_at
            cash = money(cash + entry.amount_usd)
            if cash != entry.cash_after_usd:
                raise RuntimeError(
                    f"Cash ledger row {index} balance mismatch: "
                    f"rebuilt={cash}, stored={entry.cash_after_usd}"
                )
            if entry.kind == "external_contribution":
                if entry.amount_usd <= 0:
                    raise RuntimeError("External contribution ledger amount must be positive")
                external = money(external + entry.amount_usd)
            elif entry.kind == "payout":
                if entry.amount_usd <= 0:
                    raise RuntimeError("Payout ledger amount must be positive")
                payouts = money(payouts + entry.amount_usd)
            elif entry.kind == "evaluation_fee":
                if entry.amount_usd >= 0:
                    raise RuntimeError("Evaluation fee ledger amount must be negative")
                evaluation_fees = money(evaluation_fees - entry.amount_usd)
            elif entry.kind == "activation_fee":
                if entry.amount_usd >= 0:
                    raise RuntimeError("Activation fee ledger amount must be negative")
                activation_fees = money(activation_fees - entry.amount_usd)
            else:
                raise RuntimeError(f"Unsupported cash ledger kind: {entry.kind}")

        expected = (
            self.cash_usd,
            self.external_contributions_usd,
            self.payout_receipts_usd,
            self.evaluation_fees_usd,
            self.activation_fees_usd,
        )
        rebuilt = (cash, external, payouts, evaluation_fees, activation_fees)
        if rebuilt != expected:
            raise RuntimeError(
                f"Cash ledger category mismatch: rebuilt={rebuilt}, stored={expected}"
            )
        if self.reconciliation_error_usd != 0:
            raise RuntimeError(
                f"Cash ledger reconciliation error: {self.reconciliation_error_usd}"
            )

    @property
    def reconciliation_error_usd(self) -> float:
        expected = money(
            self.external_contributions_usd
            + self.payout_receipts_usd
            - self.evaluation_fees_usd
            - self.activation_fees_usd
        )
        return money(self.cash_usd - expected)
