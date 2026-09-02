"""Per-Evaluation cycle-local one-position offer selection.

Each Evaluation runs its own selector over the whole normalized tape and
restarts it at every renewal boundary. This is deliberately not the PA book's
selector: the PA book consumes one whole-tape selection made once and never
reset, while an Evaluation re-selects inside every funded cycle. The two phases
never share a selector or a stream position.

Parent parity: reference/shared_source/evaluation.py at revision
106cfb782c6e573856282095441bb69f23924a55, which resets ``open_until`` to the
cycle start each cycle, blocks an offer entered while busy, and closes the
cycle without consuming an offer that would exit past the cycle boundary.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .evaluation import EvaluationAccount, EvaluationRules
from .inputs import TradeOffer, _causal_key


@dataclass(slots=True)
class _CycleCursor:
    """One Evaluation's position inside its current funded cycle."""

    cycle_number: int
    index: int
    open_until: datetime
    cycle_closed: bool = False


@dataclass(slots=True)
class ConsumerCounters:
    """Selector diagnostics, mirroring the pinned behavior-lock outcome."""

    admitted: int = 0
    blocked_busy: int = 0
    boundary_closed_cycles: int = 0


class CycleLocalEvaluationConsumer:
    """Offer selection for every running Evaluation in one lifecycle."""

    __slots__ = ("offers", "_entries", "_cursors", "counters")

    def __init__(self, offers: Iterable[TradeOffer]) -> None:
        ordered = tuple(sorted(offers, key=_causal_key))
        if not ordered:
            raise ValueError("Evaluation consumer requires at least one offer")
        self.offers = ordered
        self._entries = tuple(offer.entry_at for offer in ordered)
        self._cursors = {}
        self.counters = {}

    def _cursor(self, account: EvaluationAccount) -> _CycleCursor:
        cursor = self._cursors.get(account.evaluation_id)
        if cursor is None or cursor.cycle_number != account.cycle_number:
            # A new Evaluation, or a renewal boundary: restart the selector at
            # the cycle start. This reset is the whole point of the adapter.
            cursor = _CycleCursor(
                cycle_number=account.cycle_number,
                index=bisect_left(self._entries, account.cycle_started_at),
                open_until=account.cycle_started_at,
            )
            self._cursors[account.evaluation_id] = cursor
            self.counters.setdefault(account.evaluation_id, ConsumerCounters())
        return cursor

    def next_offer(
        self,
        account: EvaluationAccount,
        rules: EvaluationRules,
    ) -> TradeOffer | None:
        """The next offer this Evaluation may enter, or None for this cycle.

        Returns None when the cycle is exhausted, already closed by a
        boundary-crossing offer, or the Evaluation is not able to trade.
        """

        if account.status != "active" or account.outstanding_trade is not None:
            return None
        cursor = self._cursor(account)
        if cursor.cycle_closed:
            return None
        counters = self.counters[account.evaluation_id]
        cycle_due_at = account.cycle_due_at(rules)
        while cursor.index < len(self.offers):
            offer = self.offers[cursor.index]
            if offer.entry_at >= cycle_due_at:
                return None
            if offer.entry_at < cursor.open_until:
                counters.blocked_busy += 1
                cursor.index += 1
                continue
            if offer.exit_at > cycle_due_at:
                # Parent behavior: the cycle closes without consuming it.
                counters.boundary_closed_cycles += 1
                cursor.cycle_closed = True
                return None
            return offer
        return None

    def consume(self, account: EvaluationAccount, offer: TradeOffer) -> None:
        """Record that the Evaluation actually entered the offer."""

        cursor = self._cursor(account)
        if cursor.index >= len(self.offers) or self.offers[cursor.index] != offer:
            raise ValueError("Consumed offer is not this Evaluation's next selection")
        cursor.open_until = offer.exit_at
        cursor.index += 1
        self.counters[account.evaluation_id].admitted += 1

    def totals(self) -> ConsumerCounters:
        total = ConsumerCounters()
        for counters in self.counters.values():
            total.admitted += counters.admitted
            total.blocked_busy += counters.blocked_busy
            total.boundary_closed_cycles += counters.boundary_closed_cycles
        return total
