"""Rolling historical session-start cohort generation."""

from __future__ import annotations

from datetime import date, datetime, time

from .models import TradeOffer
from .timezones import get_timezone


def rolling_session_starts(
    offers: list[TradeOffer],
    *,
    timezone: str,
    session_open: str,
    first_date: date | None = None,
    last_date: date | None = None,
) -> list[datetime]:
    """Return one local session-open start for each date containing an offer."""

    parts = [int(part) for part in session_open.split(":")]
    if len(parts) == 2:
        parts.append(0)
    if len(parts) != 3:
        raise ValueError("session_open must be HH:MM or HH:MM:SS")
    clock = time(*parts)
    zone = get_timezone(timezone)
    dates = sorted({offer.entry_at.astimezone(zone).date() for offer in offers})
    return [
        datetime.combine(day, clock, tzinfo=zone)
        for day in dates
        if (first_date is None or day >= first_date)
        and (last_date is None or day <= last_date)
    ]

