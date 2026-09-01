"""Strict stdlib loader for the frozen RR=1 completed-trade exports."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import struct
from .models import PathOrder, TradeOffer
from .timezones import get_timezone, localize_wall_time


RAW_COLUMNS = (
    "ticket",
    "entry_time",
    "exit_time",
    "mae",
    "mfe",
    "pnl",
    "candle_range",
)
PATH_COIN_SEED = 20260823
STRATEGY_ID = "rr_r_mfe_buy_stop_entry_rr1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMPORT_MANIFEST = PROJECT_ROOT / "manifests/rr1_import_20260829.json"
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


@dataclass(frozen=True, slots=True)
class VerifiedRR1Import:
    manifest_path: Path
    manifest_sha256: str
    combined_set_sha256: str
    files: int
    bytes: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_rr1_import(
    raw_root: str | Path,
    manifest_path: str | Path = DEFAULT_IMPORT_MANIFEST,
) -> VerifiedRR1Import:
    """Bind a raw root byte-for-byte to the frozen individual-file manifest."""

    root = Path(raw_root).resolve()
    manifest = Path(manifest_path).resolve()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "rr1_import_manifest.v1":
        raise ValueError("Unsupported RR=1 import manifest schema")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 46:
        raise ValueError("RR=1 manifest must contain exactly 46 artifacts")
    expected_files: set[Path] = set()
    selected: list[tuple[str, str, int]] = []
    total_bytes = 0
    for row in artifacts:
        destination = Path(*Path(row["destination_relative_path"]).parts)
        marker = Path("data/raw/rr1")
        try:
            relative = destination.relative_to(marker)
        except ValueError as exc:
            raise ValueError(f"Manifest artifact escapes RR=1 root: {destination}") from exc
        path = (root / relative).resolve()
        if root not in path.parents:
            raise ValueError(f"Manifest artifact escapes raw root: {path}")
        if path in expected_files:
            raise ValueError(f"Duplicate manifest destination: {relative}")
        expected_files.add(path)
        expected_bytes = int(row["bytes"])
        if not path.is_file() or path.stat().st_size != expected_bytes:
            raise ValueError(f"Missing or wrong-size frozen artifact: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != row["sha256"]:
            raise ValueError(f"Frozen artifact hash mismatch: {path}")
        selected.append(
            (row["source_selection_relative_path"], actual_hash, expected_bytes)
        )
        total_bytes += expected_bytes
    actual_files = {path.resolve() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        extra = sorted(str(path) for path in actual_files - expected_files)
        missing = sorted(str(path) for path in expected_files - actual_files)
        raise ValueError(f"Frozen raw-root file set mismatch; extra={extra}, missing={missing}")
    digest = hashlib.sha256()
    for relative, file_hash, size in sorted(selected):
        digest.update(relative.replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_hash))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\n")
    combined = digest.hexdigest()
    expected_combined = payload["selection"]["combined"][
        "selected_tree_manifest_sha256"
    ]
    if combined != expected_combined:
        raise ValueError("Frozen RR=1 combined digest mismatch")
    declared = payload["selection"]["combined"]
    if int(declared["files"]) != len(expected_files) or int(declared["bytes"]) != total_bytes:
        raise ValueError("Frozen RR=1 manifest aggregate mismatch")
    return VerifiedRR1Import(
        manifest_path=manifest,
        manifest_sha256=sha256_file(manifest),
        combined_set_sha256=combined,
        files=len(expected_files),
        bytes=total_bytes,
    )


def _source_epoch_ns(value: datetime) -> int:
    """Encode a naive source label like NumPy datetime64[ns]."""

    if value.tzinfo is not None:
        raise ValueError("source epoch conversion expects a naive datetime")
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
    """Port the pinned EODMAE exit-extreme resolver without NumPy."""

    one_sided = mfe <= 0 or mae >= 0
    if not one_sided and math.isclose(pnl, mae, rel_tol=1e-5, abs_tol=1e-8):
        return "mfe_first"
    if one_sided or math.isclose(pnl, mfe, rel_tol=1e-5, abs_tol=1e-8):
        return "mae_first"
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


def _localize_source_label(label: str, zone) -> tuple[datetime, datetime]:
    naive = datetime.strptime(label, "%Y.%m.%d %H:%M:%S")
    # fold=0 is the explicit earlier-occurrence policy for an ambiguous fall-back
    # wall time. Nonexistent spring-forward labels are rejected by round-trip.
    aware = localize_wall_time(naive, zone.key, fold=0)
    return naive, aware


def _discover_kind(root: Path, stats: bool) -> dict[str, Path]:
    suffix = "_1.00_stats.csv" if stats else "_1.00.csv"
    found: dict[str, Path] = {}
    for path in root.rglob(f"*{suffix}"):
        if not path.is_file():
            continue
        if stats is False and path.name.endswith("_stats.csv"):
            continue
        window = path.name.removesuffix(suffix)
        if window not in {f"{hour}-{hour + 1}" for hour in range(1, 24)}:
            continue
        if window in found:
            raise ValueError(f"Duplicate RR=1 {window} file under {root}")
        found[window] = path
    expected = {f"{hour}-{hour + 1}" for hour in range(1, 24)}
    if set(found) != expected:
        missing = sorted(expected - set(found))
        extra = sorted(set(found) - expected)
        raise ValueError(f"RR=1 file set mismatch; missing={missing}, extra={extra}")
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


def load_rr1_offers(
    raw_root: str | Path,
    *,
    timezone: str = "Europe/Tallinn",
    commission_usd_per_mnq: float = 1.05,
    manifest_path: str | Path = DEFAULT_IMPORT_MANIFEST,
    verify_manifest: bool = True,
) -> list[TradeOffer]:
    """Load all 23 isolated-window RR=1 exports with strict validation."""

    root = Path(raw_root)
    if verify_manifest:
        verify_rr1_import(root, manifest_path)
    if not math.isfinite(commission_usd_per_mnq) or commission_usd_per_mnq < 0:
        raise ValueError("commission_usd_per_mnq must be finite and non-negative")
    zone = get_timezone(timezone)
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
                        f"{path}:{source_row}: expected {len(RAW_COLUMNS)} fields, got {len(row)}"
                    )
                ticket_text, entry_text, exit_text, mae_text, mfe_text, pnl_text, range_text = row
                try:
                    ticket = int(ticket_text)
                    mae, mfe, pnl, candle_range = map(
                        float, (mae_text, mfe_text, pnl_text, range_text)
                    )
                except ValueError as exc:
                    raise ValueError(f"{path}:{source_row}: invalid numeric value") from exc
                if not all(math.isfinite(value) for value in (mae, mfe, pnl, candle_range)):
                    raise ValueError(f"{path}:{source_row}: non-finite numeric value")
                if ticket in seen_tickets:
                    raise ValueError(f"{path}:{source_row}: duplicate ticket {ticket}")
                seen_tickets.add(ticket)
                try:
                    pnl_sum += Decimal(pnl_text)
                except InvalidOperation as exc:  # guarded above, retained for exact sum
                    raise ValueError(f"{path}:{source_row}: invalid exact P&L") from exc
                entry_naive, entry_at = _localize_source_label(entry_text, zone)
                exit_naive, exit_at = _localize_source_label(exit_text, zone)
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
                        mae_usd=mae,
                        mfe_usd=mfe,
                        gross_pnl_usd=pnl,
                        candle_range=candle_range,
                        commission_usd=float(commission_usd_per_mnq),
                        resolved_path_order=resolve_path_order(
                            entry_naive, exit_naive, mae, mfe, pnl
                        ),
                        source_file_sha256=source_hash,
                    )
                )
                row_count += 1
        stat = _read_stats(stats[window])
        if stat["run_tag"] != window or not math.isclose(float(stat["risk_reward"]), 1.0):
            raise ValueError(f"{stats[window]}: wrong run_tag or risk_reward")
        try:
            declared_trades = int(stat["trades"])
            declared_net = Decimal(stat["net_profit"])
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f"{stats[window]}: invalid count or net_profit") from exc
        if declared_trades != row_count:
            raise ValueError(
                f"{path}: {row_count} rows disagree with tester stats {stat['trades']}"
            )
        if declared_net != pnl_sum:
            raise ValueError(
                f"{path}: P&L sum {pnl_sum} disagrees with tester stats {declared_net}"
            )

    offers.sort(key=lambda row: (row.entry_at, row.window_order, row.source_row, row.ticket))
    return offers


def global_one_position_counts(offers: list[TradeOffer]) -> tuple[int, int]:
    """Return accepted/blocked counts for the Evaluation fill-time proxy."""

    accepted = blocked = 0
    open_until: datetime | None = None
    for offer in offers:
        if open_until is not None and offer.entry_at < open_until:
            blocked += 1
            continue
        accepted += 1
        open_until = offer.exit_at
    return accepted, blocked


def positive_duration_peak_overlap(offers: list[TradeOffer]) -> int:
    """Historical [entry, exit) interval depth; exits precede entries at ties."""

    events: list[tuple[datetime, int]] = []
    for offer in offers:
        if offer.exit_at <= offer.entry_at:
            continue
        events.append((offer.entry_at, 1))
        events.append((offer.exit_at, -1))
    current = peak = 0
    for _, delta in sorted(events, key=lambda event: (event[0], event[1])):
        current += delta
        peak = max(peak, current)
    return peak
