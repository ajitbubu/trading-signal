"""Orchestrates a full screener run: universe → history → fundamentals → filter.

`run` is a pure function in the sense that all I/O is delegated to the
`data_sources` modules — those modules handle caching and rate limits, so
calling `run` repeatedly in a refresh loop is safe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import pandas as pd
import structlog

from config.settings import settings
from data_sources.fundamentals import get_fundamentals_batch
from data_sources.prices import get_history
from data_sources.universe import Market, Ticker, get_universe, union_with_watchlist
from screener.filters import ScreenInputs, ScreenRow, evaluate

log = structlog.get_logger(__name__)


@dataclass
class ScreenResult:
    market: Market
    generated_at: datetime
    scanned: int
    qualified: int
    rows: list[ScreenRow]

    def to_dataframe(self) -> pd.DataFrame:
        records = [
            {
                "Ticker": r.symbol,
                "Name": r.name,
                "Price": r.price,
                "P/E": r.pe,
                "P/E (kind)": r.pe_kind,
                "Volume Ratio": r.volume_ratio,
                "RSI(14)": r.rsi,
                "Qualifies": r.qualifies,
                "Failed": ", ".join(r.failed_filters),
            }
            for r in self.rows
        ]
        return pd.DataFrame.from_records(records)


def run(
    market: Market,
    *,
    extra_symbols: Sequence[str] = (),
    pe_max: float | None = None,
    volume_ratio_min: float | None = None,
    rsi_period: int | None = None,
    rsi_min: float | None = None,
    exclude_negative_pe: bool = True,
) -> ScreenResult:
    pe_max = pe_max if pe_max is not None else settings.pe_max
    volume_ratio_min = volume_ratio_min if volume_ratio_min is not None else settings.volume_ratio_min
    rsi_period = rsi_period if rsi_period is not None else settings.rsi_period
    rsi_min = rsi_min if rsi_min is not None else settings.rsi_min

    base_universe = get_universe(market)
    universe = union_with_watchlist(base_universe, extra_symbols) if extra_symbols else base_universe

    if not universe:
        log.warning("screener_universe_empty", market=str(market))
        return ScreenResult(
            market=market,
            generated_at=datetime.now(timezone.utc),
            scanned=0,
            qualified=0,
            rows=[],
        )

    history = get_history(universe, lookback_days=60)
    fundamentals = get_fundamentals_batch(universe)

    rows: list[ScreenRow] = []
    for t in universe:
        df = history.get(t.symbol)
        if df is None or df.empty:
            continue
        row = evaluate(
            ScreenInputs(symbol=t.symbol, history=df, fundamentals=fundamentals.get(t.symbol)),
            pe_max=pe_max,
            volume_ratio_min=volume_ratio_min,
            rsi_period=rsi_period,
            rsi_min=rsi_min,
            exclude_negative_pe=exclude_negative_pe,
        )
        rows.append(row)

    qualified = [r for r in rows if r.qualifies]
    log.info(
        "screener_run",
        market=str(market),
        scanned=len(rows),
        qualified=len(qualified),
    )

    return ScreenResult(
        market=market,
        generated_at=datetime.now(timezone.utc),
        scanned=len(rows),
        qualified=len(qualified),
        rows=rows,
    )


def rank_rows(rows: Sequence[ScreenRow], by: str = "volume_ratio") -> list[ScreenRow]:
    """Default ranking. `by` is one of: 'volume_ratio' | 'composite'."""
    qualified = [r for r in rows if r.qualifies]
    if by == "composite":
        if not qualified:
            return []
        max_vr = max(r.volume_ratio for r in qualified) or 1.0
        max_rsi = max(r.rsi for r in qualified) or 1.0
        max_inv_pe = max((1.0 / r.pe) if r.pe and r.pe > 0 else 0.0 for r in qualified) or 1.0

        def score(r: ScreenRow) -> float:
            inv_pe = (1.0 / r.pe) if r.pe and r.pe > 0 else 0.0
            return (
                0.4 * (r.volume_ratio / max_vr)
                + 0.3 * (r.rsi / max_rsi)
                + 0.3 * (inv_pe / max_inv_pe)
            )

        return sorted(qualified, key=score, reverse=True)
    return sorted(qualified, key=lambda r: r.volume_ratio, reverse=True)
