from __future__ import annotations

from datetime import datetime

from eval_pa_optimal_path.models import TradeOffer
from eval_pa_optimal_path.timezones import get_timezone


ZONE = get_timezone("Europe/Tallinn")


def at(label: str) -> datetime:
    return datetime.strptime(label, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZONE)


def offer(
    key: str,
    entry: str,
    exit_: str,
    pnl: float,
    *,
    mae: float = 0.0,
    mfe: float | None = None,
    commission: float = 0.0,
    window_order: int = 1,
) -> TradeOffer:
    favorable = pnl if mfe is None else mfe
    return TradeOffer(
        trade_key=key,
        strategy_id="rr_r_mfe_buy_stop_entry_rr1",
        window_id=f"{window_order}-{window_order + 1}",
        window_order=window_order,
        source_row=1,
        ticket=window_order,
        source_entry_label=entry,
        source_exit_label=exit_,
        source_timezone_rule="Europe/Tallinn:historical_dst:fold0:gap_reject",
        entry_at=at(entry),
        exit_at=at(exit_),
        mae_usd=mae,
        mfe_usd=favorable,
        gross_pnl_usd=pnl,
        candle_range=1.0,
        commission_usd=commission,
        resolved_path_order="mae_first",
        source_file_sha256="0" * 64,
    )
