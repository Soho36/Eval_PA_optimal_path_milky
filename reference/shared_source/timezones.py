"""Timezone access with a Windows-safe Europe/Tallinn fallback.

Windows Python does not ship the IANA database. The fallback implements the EU
DST rule used by Tallinn throughout the imported 2020-2026 tape, keeping this
initial package dependency-free. If system or PyPI ``tzdata`` is present,
``zoneinfo.ZoneInfo`` remains authoritative.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


HOUR = timedelta(hours=1)
EET = timedelta(hours=2)
EEST = timedelta(hours=3)


def _last_sunday(year: int, month: int, day: int, hour: int) -> datetime:
    value = datetime(year, month, day, hour)
    return value - timedelta(days=(value.weekday() + 1) % 7)


class EuropeTallinn(tzinfo):
    """Modern Europe/Tallinn rules, including deterministic fold handling."""

    key = "Europe/Tallinn"

    @staticmethod
    def _local_transitions(year: int) -> tuple[datetime, datetime]:
        # EU clocks advance at 01:00 UTC: 03:00 EET -> 04:00 EEST.
        # They retreat at 01:00 UTC: 04:00 EEST -> 03:00 EET.
        return (
            _last_sunday(year, 3, 31, 3),
            _last_sunday(year, 10, 31, 4),
        )

    def utcoffset(self, value: datetime | None) -> timedelta | None:
        if value is None:
            return None
        naive = value.replace(tzinfo=None)
        start, end = self._local_transitions(naive.year)
        if start <= naive < start + HOUR:  # spring gap
            return EEST if value.fold else EET
        if end - HOUR <= naive < end:  # autumn repeated hour
            return EET if value.fold else EEST
        if start + HOUR <= naive < end - HOUR:
            return EEST
        return EET

    def dst(self, value: datetime | None) -> timedelta | None:
        offset = self.utcoffset(value)
        return None if offset is None else offset - EET

    def tzname(self, value: datetime | None) -> str | None:
        offset = self.utcoffset(value)
        if offset is None:
            return None
        return "EEST" if offset == EEST else "EET"

    def fromutc(self, value: datetime) -> datetime:
        if value.tzinfo is not self:
            raise ValueError("fromutc requires a datetime carrying this timezone")
        utc = value.replace(tzinfo=None)
        start_local, end_local = self._local_transitions(utc.year)
        start_utc = start_local - EET
        end_utc = end_local - EEST
        if start_utc <= utc < end_utc:
            local = utc + EEST
            fold = 0
        else:
            local = utc + EET
            fold = int(end_utc <= utc < end_utc + HOUR)
        return local.replace(tzinfo=self, fold=fold)


_TALLINN = EuropeTallinn()


def get_timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Europe/Tallinn":
            return _TALLINN
        raise


def localize_wall_time(value: datetime, name: str, *, fold: int = 0) -> datetime:
    """Strictly localize a naive wall time and reject a DST spring gap."""

    if value.tzinfo is not None:
        raise ValueError("localize_wall_time requires a naive datetime")
    if fold not in {0, 1}:
        raise ValueError("fold must be zero or one")
    zone = get_timezone(name)
    aware = value.replace(tzinfo=zone, fold=fold)
    round_trip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if round_trip != value:
        raise ValueError(f"Nonexistent {name} wall time: {value.isoformat()}")
    return aware
