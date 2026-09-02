"""Deterministic rolling-cohort boundaries for the accepted PA stream."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import hashlib
from typing import Iterable, Literal

from .inputs import AcceptedOpportunity, get_timezone, localize_wall_time


HorizonTradeDisposition = Literal[
    "outside_entry_window",
    "settle_within_horizon",
    "leave_open_unscored",
]


def session_closes_strictly_inside_trade(
    entry_at: datetime,
    exit_at: datetime,
    *,
    timezone: str = "Europe/Tallinn",
    session_close: time = time(23, 59),
) -> tuple[datetime, ...]:
    """Return payout phases at which the completed-trade copy is still open."""

    if entry_at.tzinfo is None or exit_at.tzinfo is None:
        raise ValueError("Trade timestamps must be timezone-aware")
    if exit_at < entry_at:
        raise ValueError("Trade exit cannot precede entry")
    if session_close.tzinfo is not None:
        raise ValueError("session_close must be a naive local wall-clock time")
    zone = get_timezone(timezone)
    first_date = entry_at.astimezone(zone).date()
    last_date = exit_at.astimezone(zone).date()
    close_dates = (
        first_date + timedelta(days=offset)
        for offset in range((last_date - first_date).days + 1)
    )
    closes = tuple(
        localize_wall_time(datetime.combine(close_date, session_close), timezone)
        for close_date in close_dates
    )
    return tuple(close_at for close_at in closes if entry_at < close_at < exit_at)


def classify_horizon_trade(
    entry_at: datetime,
    exit_at: datetime,
    horizon_end_at: datetime,
) -> HorizonTradeDisposition:
    """Apply the selected causal horizon-crossing contract.

    Entries at or after the horizon are outside the cohort. An opportunity
    entered before the horizon is admitted; its completed outcome is settled
    when exit_at is no later than horizon_end_at and otherwise remains open and
    unscored. No mark-to-market or post-horizon outcome is invented.
    """

    if any(value.tzinfo is None for value in (entry_at, exit_at, horizon_end_at)):
        raise ValueError("Horizon classification timestamps must be timezone-aware")
    if exit_at < entry_at:
        raise ValueError("Trade exit cannot precede entry")
    if entry_at >= horizon_end_at:
        return "outside_entry_window"
    if exit_at > horizon_end_at:
        return "leave_open_unscored"
    return "settle_within_horizon"


@dataclass(frozen=True, slots=True)
class CohortWindow:
    """One local session start and its exclusive calendar-day horizon end."""

    start_at: datetime
    horizon_end_at: datetime
    is_tape_censored: bool

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None or self.horizon_end_at.tzinfo is None:
            raise ValueError("Cohort boundaries must be timezone-aware")
        if self.horizon_end_at <= self.start_at:
            raise ValueError("Cohort horizon must follow its start")


@dataclass(frozen=True, slots=True)
class MonthlyCohortSelection:
    """Selected starts plus the complete observed/censored start inventory."""

    cohorts: tuple[CohortWindow, ...]
    all_cohorts: tuple[CohortWindow, ...]
    require_full_horizon: bool
    tape_observation_end_at: datetime

    @property
    def all_count(self) -> int:
        return len(self.all_cohorts)

    @property
    def fully_observed_count(self) -> int:
        return sum(not cohort.is_tape_censored for cohort in self.all_cohorts)

    @property
    def tape_censored_count(self) -> int:
        return sum(cohort.is_tape_censored for cohort in self.all_cohorts)


def first_session_monthly_cohorts(
    opportunities: Iterable[AcceptedOpportunity],
    *,
    horizon_days: int,
    timezone: str = "Europe/Tallinn",
    session_open: time = time(1, 0),
    require_full_horizon: bool = True,
) -> MonthlyCohortSelection:
    """Build one cohort at the first accepted-opportunity session each month.

    A valid session is a local calendar date containing at least one accepted
    PA opportunity entry. Its cohort starts at session_open on that date. The
    horizon end is exclusive and uses local calendar-day arithmetic. A start is
    tape-censored when that end is later than the last accepted opportunity exit
    present in the tape.
    """

    if (
        not isinstance(horizon_days, int)
        or isinstance(horizon_days, bool)
        or horizon_days <= 0
    ):
        raise ValueError("horizon_days must be a positive integer")
    if session_open.tzinfo is not None:
        raise ValueError("session_open must be a naive local wall-clock time")
    if not isinstance(require_full_horizon, bool):
        raise ValueError("require_full_horizon must be boolean")

    records = tuple(
        sorted(opportunities, key=lambda record: record.accepted_ordinal)
    )
    if not records:
        raise ValueError("At least one accepted opportunity is required")
    stream_hashes = {record.accepted_stream_sha256 for record in records}
    raw_counts = {record.raw_offer_count for record in records}
    if len(stream_hashes) != 1 or len(raw_counts) != 1:
        raise ValueError("Cohorts require one internally consistent accepted stream")
    if tuple(record.accepted_ordinal for record in records) != tuple(
        range(1, len(records) + 1)
    ):
        raise ValueError("Cohorts require a complete accepted stream from ordinal one")
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.offer.trade_key.encode("utf-8"))
        digest.update(b"\n")
    if digest.hexdigest() != records[0].accepted_stream_sha256:
        raise ValueError("Accepted opportunity records do not match their stream digest")

    zone = get_timezone(timezone)
    entry_dates = sorted(
        {record.offer.entry_at.astimezone(zone).date() for record in records}
    )
    first_date_by_month = {}
    for entry_date in entry_dates:
        first_date_by_month.setdefault(
            (entry_date.year, entry_date.month),
            entry_date,
        )

    tape_observation_end_at = max(
        record.offer.exit_at.astimezone(zone) for record in records
    )
    cohort_rows = []
    for entry_date in first_date_by_month.values():
        start_at = localize_wall_time(
            datetime.combine(entry_date, session_open),
            timezone,
        )
        horizon_end_at = start_at + timedelta(days=horizon_days)
        cohort_rows.append(
            CohortWindow(
                start_at=start_at,
                horizon_end_at=horizon_end_at,
                is_tape_censored=horizon_end_at > tape_observation_end_at,
            )
        )
    all_cohorts = tuple(cohort_rows)
    cohorts = (
        tuple(cohort for cohort in all_cohorts if not cohort.is_tape_censored)
        if require_full_horizon
        else all_cohorts
    )
    return MonthlyCohortSelection(
        cohorts=cohorts,
        all_cohorts=all_cohorts,
        require_full_horizon=require_full_horizon,
        tape_observation_end_at=tape_observation_end_at,
    )
