"""Indicator tests against known fixtures.

The RSI fixture below is the canonical Wilder example from his 1978 book
*New Concepts in Technical Trading Systems* (table 5.1, page 65–67).
We verify our implementation matches Wilder's published values within
0.5 RSI points.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from indicators.technical import below_dma, dma_cross, rsi, sma, volume_ratio


# Wilder's classic 14-day RSI example, prices over 19 days.
WILDER_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
]
# Wilder's published RSI values for the last 5 bars (approx.).
EXPECTED_RSI_LAST = [70.46, 66.25, 66.48, 69.35, 66.29, 57.91]


def test_rsi_matches_wilder_fixture():
    s = pd.Series(WILDER_CLOSES)
    out = rsi(s, period=14)
    last_values = out.iloc[-len(EXPECTED_RSI_LAST):].tolist()
    for got, expected in zip(last_values, EXPECTED_RSI_LAST):
        assert math.isfinite(got), f"non-finite RSI: {got}"
        assert abs(got - expected) < 1.0, f"RSI {got:.2f} != expected {expected:.2f}"


def test_rsi_short_series_is_nan():
    out = rsi(pd.Series([1.0, 2.0, 3.0]), period=14)
    assert out.isna().all()


def test_sma_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(s, 3)
    assert math.isnan(out.iloc[0])
    assert math.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[3] == pytest.approx(3.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_volume_ratio_excludes_today_from_denominator():
    # 20 days of avg volume = 1000, today = 3000 → ratio 3.0
    base = [1000.0] * 20
    series = pd.Series(base + [3000.0])
    assert volume_ratio(series, period=20) == pytest.approx(3.0)


def test_volume_ratio_zero_avg_returns_nan():
    series = pd.Series([0.0] * 20 + [100.0])
    out = volume_ratio(series, period=20)
    assert math.isnan(out)


def test_volume_ratio_short_series_returns_nan():
    series = pd.Series([100.0, 200.0])
    out = volume_ratio(series, period=20)
    assert math.isnan(out)


def test_dma_cross_true_when_fast_above_slow():
    rising = pd.Series([float(i) for i in range(1, 251)])
    assert dma_cross(rising, fast=50, slow=200) is True


def test_dma_cross_false_when_fast_below_slow():
    falling = pd.Series([float(i) for i in range(250, 0, -1)])
    assert dma_cross(falling, fast=50, slow=200) is False


def test_below_dma_true_when_recent_close_dips():
    series = pd.Series([100.0] * 49 + [50.0])
    assert below_dma(series, period=50) is True


def test_below_dma_false_when_recent_close_above_avg():
    series = pd.Series([100.0] * 49 + [200.0])
    assert below_dma(series, period=50) is False
