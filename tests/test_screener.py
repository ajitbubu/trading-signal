"""Filter pipeline tests with synthetic OHLCV.

We feed the evaluator a hand-built DataFrame so the test is hermetic — no
yfinance, no diskcache. The `Fundamentals` object is constructed directly.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from data_sources.fundamentals import Fundamentals
from screener.filters import ScreenInputs, evaluate
from screener.runner import rank_rows
from screener.filters import ScreenRow


def _rising_history(n: int = 30, base_volume: float = 1000.0, vol_spike: float = 5000.0) -> pd.DataFrame:
    closes = [100.0 + i for i in range(n)]
    volumes = [base_volume] * (n - 1) + [vol_spike]
    return pd.DataFrame({"Close": closes, "Volume": volumes})


def _flat_history(n: int = 30, price: float = 100.0, volume: float = 1000.0) -> pd.DataFrame:
    return pd.DataFrame({"Close": [price] * n, "Volume": [volume] * n})


def _fundamentals(symbol: str, pe: float | None, kind: str | None = "trailing") -> Fundamentals:
    return Fundamentals(
        symbol=symbol, name=symbol, sector="Tech",
        pe_trailing=pe if kind == "trailing" else None,
        pe_forward=pe if kind == "forward" else None,
        pe_used=pe, pe_used_kind=kind if pe is not None else None,
    )


def test_qualifies_when_all_three_filters_pass():
    inp = ScreenInputs(symbol="ACME", history=_rising_history(),
                       fundamentals=_fundamentals("ACME", pe=15.0))
    row = evaluate(inp, pe_max=20.0, volume_ratio_min=2.0,
                   rsi_period=14, rsi_min=50.0, exclude_negative_pe=True)
    assert row.qualifies is True
    assert row.failed_filters == []
    assert row.volume_ratio == pytest.approx(5.0)


def test_fails_when_pe_above_max():
    inp = ScreenInputs(symbol="HIGHPE", history=_rising_history(),
                       fundamentals=_fundamentals("HIGHPE", pe=30.0))
    row = evaluate(inp, pe_max=20.0, volume_ratio_min=2.0,
                   rsi_period=14, rsi_min=50.0, exclude_negative_pe=True)
    assert row.qualifies is False
    assert "pe_above_max" in row.failed_filters


def test_fails_when_pe_unavailable_and_excluding():
    inp = ScreenInputs(symbol="NOPE", history=_rising_history(),
                       fundamentals=_fundamentals("NOPE", pe=None, kind=None))
    row = evaluate(inp, pe_max=20.0, volume_ratio_min=2.0,
                   rsi_period=14, rsi_min=50.0, exclude_negative_pe=True)
    assert row.qualifies is False
    assert "pe_unavailable" in row.failed_filters


def test_fails_when_volume_ratio_below_threshold():
    inp = ScreenInputs(symbol="CALM",
                       history=_rising_history(vol_spike=1100.0),  # 1.1× avg
                       fundamentals=_fundamentals("CALM", pe=10.0))
    row = evaluate(inp, pe_max=20.0, volume_ratio_min=2.0,
                   rsi_period=14, rsi_min=50.0, exclude_negative_pe=True)
    assert row.qualifies is False
    assert "volume_below_threshold" in row.failed_filters


def test_fails_when_rsi_below_threshold():
    # Flat prices → RSI neutral around 50; we need <= 50 to fail the >50 check.
    inp = ScreenInputs(symbol="FLAT", history=_flat_history(volume=1000.0),
                       fundamentals=_fundamentals("FLAT", pe=10.0))
    # Force volume ratio to pass by bumping last bar.
    inp.history.loc[len(inp.history) - 1, "Volume"] = 5000.0
    row = evaluate(inp, pe_max=20.0, volume_ratio_min=2.0,
                   rsi_period=14, rsi_min=50.0, exclude_negative_pe=True)
    assert row.qualifies is False
    assert "rsi_below_threshold" in row.failed_filters


def test_forward_pe_flagged():
    inp = ScreenInputs(symbol="FWD", history=_rising_history(),
                       fundamentals=_fundamentals("FWD", pe=15.0, kind="forward"))
    row = evaluate(inp, pe_max=20.0, volume_ratio_min=2.0,
                   rsi_period=14, rsi_min=50.0, exclude_negative_pe=True)
    assert row.qualifies is True
    assert row.pe_kind == "forward"


def test_rank_by_volume_ratio_desc_only_qualified():
    rows = [
        ScreenRow("A", "A", 100, 10.0, "trailing", 5.0, 60, True, []),
        ScreenRow("B", "B", 100, 10.0, "trailing", 8.0, 60, True, []),
        ScreenRow("C", "C", 100, 10.0, "trailing", 2.5, 60, True, []),
        ScreenRow("D", "D", 100, 30.0, "trailing", 9.0, 60, False, ["pe_above_max"]),
    ]
    ranked = rank_rows(rows, by="volume_ratio")
    assert [r.symbol for r in ranked] == ["B", "A", "C"]


def test_rank_composite_excludes_failures():
    rows = [
        ScreenRow("A", "A", 100, 10.0, "trailing", 5.0, 60, True, []),
        ScreenRow("B", "B", 100, 5.0, "trailing", 3.0, 70, True, []),
        ScreenRow("C", "C", 100, 30.0, "trailing", 10.0, 90, False, ["pe_above_max"]),
    ]
    ranked = rank_rows(rows, by="composite")
    assert all(r.qualifies for r in ranked)
    assert "C" not in [r.symbol for r in ranked]
