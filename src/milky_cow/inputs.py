"""Strict RR1 import verification, normalization, and global selection.

Implementation provenance:
- reviewed parent repository I:/PycharmProjects/Eval_PA_optimal_path
- parent revision 106cfb782c6e573856282095441bb69f23924a55
- reference/shared_source/io.py SHA-256
  407fe564721fae4027a5638dfeafa1f71fd34600ffdcf995c2588f7b72310c12
- reference/shared_source/models.py SHA-256
  26ceb06fc1aa1d32db41a595e1ceb1a904c83ca3577b000d91db14e068bfa9f4
- reference/shared_source/timezones.py SHA-256
  39ea226a64494b5bb3c9d857a03d4b198ef886f481cb032f037a63e414aec513

This is a selective copy-to-all adaptation. Routing and overlap-capacity helpers
from the parent were deliberately not imported.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import struct
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PathOrder = Literal["mae_first", "mfe_first"]
PathStressArm = Literal[
    "source_constrained_then_mae_first",
    "source_constrained_then_mfe_first",
    "source_constrained_then_seeded_coin",
]
IntratradePathStatus = Literal["source_constrained", "ambiguous"]
RAW_COLUMNS = (
    "ticket",
    "entry_time",
    "exit_time",
    "mae",
    "mfe",
    "pnl",
    "candle_range",
)
STATS_COLUMNS = (
    "run_tag",
    "risk_reward",
    "trades",
    "net_profit",
    "gross_profit",
    "gross_loss",
    "equity_dd",
    "balance_dd",
    "profit_factor",
    "expected_payoff",
    "recovery_factor",
    "sharpe",
)
PATH_COIN_SEED = 20260823
EXPECTED_RAW_OFFERS = 12_658
EXPECTED_ACCEPTED_OPPORTUNITIES = 9_299
EXPECTED_BLOCKED_OFFERS = 3_359
EXPECTED_ACCEPTED_STREAM_SHA256 = (
    "1175787ba50f0ab9f08a953f60b661e597c70f2bdb9329a517603616aaae6759"
)
STRATEGY_ID = "rr_r_mfe_buy_stop_entry_rr1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMPORT_MANIFEST = PROJECT_ROOT / "manifests/rr1_import_20260829.json"


def money(value: float) -> float:
    return round(float(value), 2)


@dataclass(frozen=True, slots=True)
class TradeOffer:
    trade_key: str
    strategy_id: str
    window_id: str
    window_order: int
    source_row: int
    ticket: int
    source_entry_label: str
    source_exit_label: str
    source_timezone_rule: str
    entry_at: datetime
    exit_at: datetime
    mae_usd_per_mnq: float
    mfe_usd_per_mnq: float
    gross_pnl_usd_per_mnq: float
    candle_range: float
    commission_usd_per_mnq: float
    resolved_path_order: PathOrder
    source_file_sha256: str

    def __post_init__(self) -> None:
        if not self.trade_key or not self.strategy_id or not self.source_timezone_rule:
            raise ValueError("Trade identity and timezone provenance are required")
        if self.entry_at.tzinfo is None or self.exit_at.tzinfo is None:
            raise ValueError("Trade timestamps must be timezone-aware")
        if self.exit_at < self.entry_at:
            raise ValueError("Trade exit precedes entry")
        if (
            not isinstance(self.window_order, int)
            or isinstance(self.window_order, bool)
            or not 1 <= self.window_order <= 23
            or not isinstance(self.source_row, int)
            or isinstance(self.source_row, bool)
            or self.source_row < 1
            or not isinstance(self.ticket, int)
            or isinstance(self.ticket, bool)
        ):
            raise ValueError("Trade source coordinates are invalid")
        if self.resolved_path_order not in {"mae_first", "mfe_first"}:
            raise ValueError("Trade path order must be resolved")
        if len(self.source_file_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_file_sha256
        ):
            raise ValueError("Trade source SHA-256 must be lowercase hexadecimal")
        numeric = (
            self.mae_usd_per_mnq,
            self.mfe_usd_per_mnq,
            self.gross_pnl_usd_per_mnq,
            self.candle_range,
            self.commission_usd_per_mnq,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("Trade numeric values must be finite")
        if self.commission_usd_per_mnq < 0:
            raise ValueError("Commission cannot be negative")

    @property
    def net_pnl_usd_per_mnq(self) -> float:
        return money(
            self.gross_pnl_usd_per_mnq - self.commission_usd_per_mnq
        )

    @property
    def entry_trading_day(self) -> date:
        return self.entry_at.date()

    @property
    def exit_trading_day(self) -> date:
        return self.exit_at.date()

    @property
    def intratrade_path_status(self) -> IntratradePathStatus:
        constrained = source_constrained_path_order(
            self.mae_usd_per_mnq,
            self.mfe_usd_per_mnq,
            self.gross_pnl_usd_per_mnq,
        )
        return "source_constrained" if constrained is not None else "ambiguous"


@dataclass(frozen=True, slots=True)
class VerifiedRR1Import:
    manifest_path: Path
    manifest_sha256: str
    combined_set_sha256: str
    files: int
    bytes: int


def _causal_key(offer: TradeOffer) -> tuple[datetime, int, int, int]:
    return (
        offer.entry_at,
        offer.window_order,
        offer.source_row,
        offer.ticket,
    )


@dataclass(frozen=True, slots=True)
class AcceptedOpportunity:
    """Evidence that an offer belongs to one validated selector output."""

    offer: TradeOffer
    selector_id: Literal["whole_verified_tape_once"]
    accepted_stream_sha256: str
    accepted_ordinal: int
    raw_offer_count: int

    def __post_init__(self) -> None:
        if self.selector_id != "whole_verified_tape_once":
            raise ValueError("Unsupported opportunity selector")
        if len(self.accepted_stream_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.accepted_stream_sha256
        ):
            raise ValueError("Accepted-stream SHA-256 must be lowercase hexadecimal")
        if (
            not isinstance(self.accepted_ordinal, int)
            or isinstance(self.accepted_ordinal, bool)
            or self.accepted_ordinal <= 0
            or not isinstance(self.raw_offer_count, int)
            or isinstance(self.raw_offer_count, bool)
            or self.raw_offer_count < self.accepted_ordinal
        ):
            raise ValueError("Accepted opportunity ordinals are invalid")


@dataclass(frozen=True, slots=True)
class OpportunitySelection:
    accepted: tuple[TradeOffer, ...]
    blocked: tuple[TradeOffer, ...]

    def __post_init__(self) -> None:
        combined = self.accepted + self.blocked
        trade_keys = [offer.trade_key for offer in combined]
        if len(trade_keys) != len(set(trade_keys)):
            raise ValueError("Opportunity selector input contains duplicate trade keys")
        expected_accepted: list[TradeOffer] = []
        expected_blocked: list[TradeOffer] = []
        open_until: datetime | None = None
        for offer in sorted(combined, key=_causal_key):
            if open_until is not None and offer.entry_at < open_until:
                expected_blocked.append(offer)
            else:
                expected_accepted.append(offer)
                open_until = offer.exit_at
        if tuple(expected_accepted) != self.accepted or tuple(expected_blocked) != self.blocked:
            raise ValueError("Opportunity selection is not the causal one-position partition")

    @property
    def raw_count(self) -> int:
        return len(self.accepted) + len(self.blocked)

    @property
    def accepted_stream_sha256(self) -> str:
        digest = hashlib.sha256()
        for offer in self.accepted:
            digest.update(offer.trade_key.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    @property
    def accepted_opportunities(self) -> tuple[AcceptedOpportunity, ...]:
        stream_hash = self.accepted_stream_sha256
        return tuple(
            AcceptedOpportunity(
                offer=offer,
                selector_id="whole_verified_tape_once",
                accepted_stream_sha256=stream_hash,
                accepted_ordinal=ordinal,
                raw_offer_count=self.raw_count,
            )
            for ordinal, offer in enumerate(self.accepted, start=1)
        )


@dataclass(frozen=True, slots=True)
class VerifiedRR1Dataset:
    """One fresh integrity check plus one normalized, selected in-memory tape."""

    verification: VerifiedRR1Import
    offers: tuple[TradeOffer, ...]
    selection: OpportunitySelection


HOUR = timedelta(hours=1)
EET = timedelta(hours=2)
EEST = timedelta(hours=3)


def _last_sunday(year: int, month: int, day: int, hour: int) -> datetime:
    value = datetime(year, month, day, hour)
    return value - timedelta(days=(value.weekday() + 1) % 7)


class EuropeTallinn(tzinfo):
    """Modern Tallinn rules for the 2020-2026 tape when tzdata is unavailable."""

    key = "Europe/Tallinn"

    @staticmethod
    def _local_transitions(year: int) -> tuple[datetime, datetime]:
        return (
            _last_sunday(year, 3, 31, 3),
            _last_sunday(year, 10, 31, 4),
        )

    def utcoffset(self, value: datetime | None) -> timedelta | None:
        if value is None:
            return None
        naive = value.replace(tzinfo=None)
        start, end = self._local_transitions(naive.year)
        if start <= naive < start + HOUR:
            return EEST if value.fold else EET
        if end - HOUR <= naive < end:
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
            raise ValueError("fromutc requires this Tallinn timezone")
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


@lru_cache(maxsize=None)
def get_timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Europe/Tallinn":
            return _TALLINN
        raise


def localize_wall_time(value: datetime, name: str, *, fold: int = 0) -> datetime:
    if value.tzinfo is not None:
        raise ValueError("Wall-time localization requires a naive datetime")
    if fold not in {0, 1}:
        raise ValueError("fold must be zero or one")
    zone = get_timezone(name)
    aware = value.replace(tzinfo=zone, fold=fold)
    round_trip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if round_trip != value:
        raise ValueError(f"Nonexistent {name} wall time: {value.isoformat()}")
    return aware


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_destination_relative(destination: str) -> Path:
    pure = PurePosixPath(destination)
    marker = ("data", "raw", "rr1")
    if pure.is_absolute() or tuple(pure.parts[:3]) != marker:
        raise ValueError(f"RR1 manifest destination escapes root: {destination}")
    relative = pure.parts[3:]
    if not relative or ".." in relative:
        raise ValueError(f"Invalid RR1 manifest destination: {destination}")
    return Path(*relative)


def verify_rr1_import(
    raw_root: str | Path,
    manifest_path: str | Path = DEFAULT_IMPORT_MANIFEST,
) -> VerifiedRR1Import:
    root = Path(raw_root).resolve()
    manifest = Path(manifest_path).resolve()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "rr1_import_manifest.v1":
        raise ValueError("Unsupported RR1 import manifest schema")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 46:
        raise ValueError("RR1 manifest must contain exactly 46 artifacts")

    expected_files: set[Path] = set()
    selected: list[tuple[str, str, int]] = []
    total_bytes = 0
    for row in artifacts:
        relative = _manifest_destination_relative(
            row["destination_relative_path"]
        )
        path = (root / relative).resolve()
        if root not in path.parents:
            raise ValueError(f"RR1 artifact escapes raw root: {path}")
        if path in expected_files:
            raise ValueError(f"Duplicate RR1 manifest destination: {relative}")
        expected_files.add(path)
        expected_bytes = int(row["bytes"])
        if not path.is_file() or path.stat().st_size != expected_bytes:
            raise ValueError(f"Missing or wrong-size RR1 artifact: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != row["sha256"]:
            raise ValueError(f"RR1 artifact hash mismatch: {path}")
        selected.append(
            (row["source_selection_relative_path"], actual_hash, expected_bytes)
        )
        total_bytes += expected_bytes

    actual_files = {path.resolve() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        extra = sorted(str(path) for path in actual_files - expected_files)
        missing = sorted(str(path) for path in expected_files - actual_files)
        raise ValueError(f"RR1 file-set mismatch; extra={extra}, missing={missing}")

    digest = hashlib.sha256()
    for relative, file_hash, size in sorted(selected):
        digest.update(relative.replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_hash))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\n")
    combined = digest.hexdigest()
    declared = payload["selection"]["combined"]
    if combined != declared["selected_tree_manifest_sha256"]:
        raise ValueError("RR1 combined digest mismatch")
    if int(declared["files"]) != len(expected_files) or int(
        declared["bytes"]
    ) != total_bytes:
        raise ValueError("RR1 manifest aggregate mismatch")

    return VerifiedRR1Import(
        manifest_path=manifest,
        manifest_sha256=sha256_file(manifest),
        combined_set_sha256=combined,
        files=len(expected_files),
        bytes=total_bytes,
    )


def _source_epoch_ns(value: datetime) -> int:
    if value.tzinfo is not None:
        raise ValueError("Source epoch conversion requires a naive datetime")
    return int(value.replace(tzinfo=UTC).timestamp()) * 1_000_000_000


def resolve_path_order(
    entry_label: datetime,
    exit_label: datetime,
    mae: float,
    mfe: float,
    pnl: float,
    *,
    seed: int = PATH_COIN_SEED,
) -> PathOrder:
    """Preserve the pinned upstream resolver for the Evaluation behavior lock."""

    one_sided = mfe <= 0 or mae >= 0
    if not one_sided and math.isclose(pnl, mae, rel_tol=1e-5, abs_tol=1e-8):
        return "mfe_first"
    if one_sided or math.isclose(pnl, mfe, rel_tol=1e-5, abs_tol=1e-8):
        return "mae_first"
    return seeded_ambiguous_path_order(entry_label, exit_label, mae, mfe, pnl, seed=seed)


def seeded_ambiguous_path_order(
    entry_label: datetime,
    exit_label: datetime,
    mae: float,
    mfe: float,
    pnl: float,
    *,
    seed: int = PATH_COIN_SEED,
) -> PathOrder:
    """Deterministically impute one order without claiming it was observed."""

    keys = (
        _source_epoch_ns(entry_label),
        _source_epoch_ns(exit_label),
        round(mae * 100),
        round(mfe * 100),
        round(pnl * 100),
    )
    payload = seed.to_bytes(8, "big", signed=True) + struct.pack("<5q", *keys)
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return "mfe_first" if digest[-1] & 1 else "mae_first"


def source_constrained_path_order(
    mae: float,
    mfe: float,
    pnl: float,
) -> PathOrder | None:
    """Return a settlement-effective constraint, else a two-sided ambiguity.

    A two-sided trade ending at MAE guarantees an adverse endpoint after any
    earlier MFE, which is sufficient for trailing-drawdown settlement. Ending
    at MFE does not exclude an earlier MFE -> MAE excursion and therefore does
    not prove MAE-first order.
    """

    if not all(math.isfinite(value) for value in (mae, mfe, pnl)):
        raise ValueError("Path extrema and closing P&L must be finite")
    one_sided = mfe <= 0 or mae >= 0
    if one_sided:
        return "mae_first"
    if math.isclose(pnl, mae, rel_tol=1e-5, abs_tol=1e-8):
        return "mfe_first"
    return None


def path_order_for_offer(
    offer: TradeOffer,
    stress_arm: PathStressArm,
) -> PathOrder:
    """Apply stress only where the completed-trade endpoints leave order unknown."""

    arms: dict[str, PathOrder | Literal["seeded_coin"]] = {
        "source_constrained_then_mae_first": "mae_first",
        "source_constrained_then_mfe_first": "mfe_first",
        "source_constrained_then_seeded_coin": "seeded_coin",
    }
    if stress_arm not in arms:
        raise ValueError("Unsupported intratrade path stress arm")
    constrained = source_constrained_path_order(
        offer.mae_usd_per_mnq,
        offer.mfe_usd_per_mnq,
        offer.gross_pnl_usd_per_mnq,
    )
    if constrained is not None:
        return constrained
    ambiguous_resolution = arms[stress_arm]
    return (
        seeded_ambiguous_path_order(
            offer.entry_at.replace(tzinfo=None),
            offer.exit_at.replace(tzinfo=None),
            offer.mae_usd_per_mnq,
            offer.mfe_usd_per_mnq,
            offer.gross_pnl_usd_per_mnq,
        )
        if ambiguous_resolution == "seeded_coin"
        else ambiguous_resolution
    )


def _discover_kind(root: Path, *, stats: bool) -> dict[str, Path]:
    suffix = "_1.00_stats.csv" if stats else "_1.00.csv"
    found: dict[str, Path] = {}
    for path in root.rglob(f"*{suffix}"):
        if not path.is_file():
            continue
        if not stats and path.name.endswith("_stats.csv"):
            continue
        window = path.name.removesuffix(suffix)
        if window not in {f"{hour}-{hour + 1}" for hour in range(1, 24)}:
            continue
        if window in found:
            raise ValueError(f"Duplicate RR1 {window} file")
        found[window] = path
    expected = {f"{hour}-{hour + 1}" for hour in range(1, 24)}
    if set(found) != expected:
        raise ValueError(
            f"RR1 window set mismatch; missing={sorted(expected - set(found))}, "
            f"extra={sorted(set(found) - expected)}"
        )
    return found


def _read_stats(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-16", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != STATS_COLUMNS:
            raise ValueError(f"{path}: stats schema mismatch")
        rows = list(reader)
    if len(rows) != 1:
        raise ValueError(f"{path}: expected one stats row, got {len(rows)}")
    return rows[0]


def _localize_label(label: str, timezone: str) -> tuple[datetime, datetime]:
    naive = datetime.strptime(label, "%Y.%m.%d %H:%M:%S")
    return naive, localize_wall_time(naive, timezone, fold=0)


def _load_rr1_offers_unverified(
    raw_root: str | Path,
    *,
    timezone: str = "Europe/Tallinn",
    commission_usd_per_mnq: float = 1.05,
) -> list[TradeOffer]:
    root = Path(raw_root)
    if not math.isfinite(commission_usd_per_mnq) or commission_usd_per_mnq < 0:
        raise ValueError("Commission must be finite and non-negative")
    trades = _discover_kind(root, stats=False)
    stats = _discover_kind(root, stats=True)
    offers: list[TradeOffer] = []
    seen_keys: set[str] = set()

    for hour in range(1, 24):
        window = f"{hour}-{hour + 1}"
        path = trades[window]
        source_hash = sha256_file(path)
        row_count = 0
        pnl_sum = Decimal("0")
        seen_tickets: set[int] = set()
        with path.open("r", encoding="utf-16", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            for source_row, row in enumerate(reader, start=1):
                if len(row) != len(RAW_COLUMNS):
                    raise ValueError(
                        f"{path}:{source_row}: expected seven fields, got {len(row)}"
                    )
                (
                    ticket_text,
                    entry_text,
                    exit_text,
                    mae_text,
                    mfe_text,
                    pnl_text,
                    range_text,
                ) = row
                try:
                    ticket = int(ticket_text)
                    mae, mfe, pnl, candle_range = map(
                        float, (mae_text, mfe_text, pnl_text, range_text)
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"{path}:{source_row}: invalid numeric value"
                    ) from exc
                if not all(
                    math.isfinite(value)
                    for value in (mae, mfe, pnl, candle_range)
                ):
                    raise ValueError(f"{path}:{source_row}: non-finite value")
                if ticket in seen_tickets:
                    raise ValueError(f"{path}:{source_row}: duplicate ticket")
                seen_tickets.add(ticket)
                try:
                    pnl_sum += Decimal(pnl_text)
                except InvalidOperation as exc:
                    raise ValueError(f"{path}:{source_row}: invalid P&L") from exc
                entry_naive, entry_at = _localize_label(entry_text, timezone)
                exit_naive, exit_at = _localize_label(exit_text, timezone)
                key = f"rr1:{window}:{source_row}:{ticket}"
                if key in seen_keys:
                    raise ValueError(f"Duplicate trade key: {key}")
                seen_keys.add(key)
                offers.append(
                    TradeOffer(
                        trade_key=key,
                        strategy_id=STRATEGY_ID,
                        window_id=window,
                        window_order=hour,
                        source_row=source_row,
                        ticket=ticket,
                        source_entry_label=entry_text,
                        source_exit_label=exit_text,
                        source_timezone_rule=(
                            f"{timezone}:historical_dst:fold0:gap_reject"
                        ),
                        entry_at=entry_at,
                        exit_at=exit_at,
                        mae_usd_per_mnq=mae,
                        mfe_usd_per_mnq=mfe,
                        gross_pnl_usd_per_mnq=pnl,
                        candle_range=candle_range,
                        commission_usd_per_mnq=float(
                            commission_usd_per_mnq
                        ),
                        resolved_path_order=resolve_path_order(
                            entry_naive, exit_naive, mae, mfe, pnl
                        ),
                        source_file_sha256=source_hash,
                    )
                )
                row_count += 1

        stat = _read_stats(stats[window])
        if stat["run_tag"] != window or not math.isclose(
            float(stat["risk_reward"]), 1.0
        ):
            raise ValueError(f"{stats[window]}: wrong run tag or RR")
        try:
            declared_trades = int(stat["trades"])
            declared_net = Decimal(stat["net_profit"])
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f"{stats[window]}: invalid stats totals") from exc
        if declared_trades != row_count or declared_net != pnl_sum:
            raise ValueError(
                f"{path}: raw rows/P&L disagree with companion stats"
            )

    offers.sort(
        key=lambda row: (
            row.entry_at,
            row.window_order,
            row.source_row,
            row.ticket,
        )
    )
    return offers


def load_rr1_offers(
    raw_root: str | Path,
    *,
    timezone: str = "Europe/Tallinn",
    commission_usd_per_mnq: float = 1.05,
    manifest_path: str | Path = DEFAULT_IMPORT_MANIFEST,
) -> list[TradeOffer]:
    """Freshly verify every imported artifact before normalizing any offers."""

    verify_rr1_import(raw_root, manifest_path)
    return _load_rr1_offers_unverified(
        raw_root,
        timezone=timezone,
        commission_usd_per_mnq=commission_usd_per_mnq,
    )


def load_verified_rr1_dataset(
    raw_root: str | Path,
    *,
    timezone: str = "Europe/Tallinn",
    commission_usd_per_mnq: float = 1.05,
    manifest_path: str | Path = DEFAULT_IMPORT_MANIFEST,
) -> VerifiedRR1Dataset:
    """Verify once, then normalize and select without a second integrity pass."""

    verification = verify_rr1_import(raw_root, manifest_path)
    offers = tuple(
        _load_rr1_offers_unverified(
            raw_root,
            timezone=timezone,
            commission_usd_per_mnq=commission_usd_per_mnq,
        )
    )
    selection = select_global_one_position(list(offers))
    observed = (
        len(offers),
        len(selection.accepted),
        len(selection.blocked),
        selection.accepted_stream_sha256,
    )
    expected = (
        EXPECTED_RAW_OFFERS,
        EXPECTED_ACCEPTED_OPPORTUNITIES,
        EXPECTED_BLOCKED_OFFERS,
        EXPECTED_ACCEPTED_STREAM_SHA256,
    )
    if observed != expected:
        raise ValueError(f"Verified RR1 selection parity mismatch: {observed} != {expected}")
    return VerifiedRR1Dataset(
        verification=verification,
        offers=offers,
        selection=selection,
    )


def select_global_one_position(
    offers: list[TradeOffer],
) -> OpportunitySelection:
    """Select the exogenous whole-tape PA opportunity stream exactly once."""

    ordered = sorted(offers, key=_causal_key)
    accepted: list[TradeOffer] = []
    blocked: list[TradeOffer] = []
    open_until: datetime | None = None
    for offer in ordered:
        if open_until is not None and offer.entry_at < open_until:
            blocked.append(offer)
            continue
        accepted.append(offer)
        open_until = offer.exit_at
    return OpportunitySelection(tuple(accepted), tuple(blocked))
