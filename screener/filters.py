"""Pure-function filters. Operate on a single ticker's bundled data."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data_sources.fundamentals import Fundamentals
from indicators.technical import rsi, volume_ratio


@dataclass
class ScreenInputs:
    symbol: str
    history: pd.DataFrame   # must contain Close, Volume
    fundamentals: Fundamentals | None


@dataclass
class ScreenRow:
    symbol: str
    name: str | None
    price: float
    pe: float | None
    pe_kind: str | None     # "trailing" | "forward"
    volume_ratio: float
    rsi: float
    qualifies: bool
    failed_filters: list[str]


def evaluate(
    inp: ScreenInputs,
    *,
    pe_max: float,
    volume_ratio_min: float,
    rsi_period: int,
    rsi_min: float,
    exclude_negative_pe: bool,
) -> ScreenRow:
    failed: list[str] = []

    close = inp.history["Close"] if "Close" in inp.history.columns else None
    volume = inp.history["Volume"] if "Volume" in inp.history.columns else None
    last_price = float(close.iloc[-1]) if close is not None and len(close) else float("nan")

    pe_value = inp.fundamentals.pe_used if inp.fundamentals else None
    pe_kind = inp.fundamentals.pe_used_kind if inp.fundamentals else None

    if pe_value is None:
        if exclude_negative_pe:
            failed.append("pe_unavailable")
    elif pe_value >= pe_max:
        failed.append("pe_above_max")

    vr = volume_ratio(volume, period=20) if volume is not None else float("nan")
    if pd.isna(vr) or vr < volume_ratio_min:
        failed.append("volume_below_threshold")

    rsi_series = rsi(close, period=rsi_period) if close is not None else None
    rsi_last = float(rsi_series.iloc[-1]) if rsi_series is not None and len(rsi_series) else float("nan")
    if pd.isna(rsi_last) or rsi_last <= rsi_min:
        failed.append("rsi_below_threshold")

    qualifies = not failed
    return ScreenRow(
        symbol=inp.symbol,
        name=inp.fundamentals.name if inp.fundamentals else None,
        price=last_price,
        pe=pe_value,
        pe_kind=pe_kind,
        volume_ratio=vr if not pd.isna(vr) else float("nan"),
        rsi=rsi_last if not pd.isna(rsi_last) else float("nan"),
        qualifies=qualifies,
        failed_filters=failed,
    )
