"""Pure technical-indicator math. No I/O.

The screener and signal engine call into here with a price DataFrame and
get back deterministic numbers that can be unit-tested in isolation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI on a close series.

    Seed = SMA of first `period` gains/losses (Wilder, 1978). After the
    seed, smoothing is `avg_t = (avg_{t-1} * (period - 1) + x_t) / period`.

    Edge cases:
      - If both avg_gain and avg_loss are zero (perfectly flat series),
        RSI is reported as 50 (neutral) rather than 100.
      - If avg_loss is zero but avg_gain > 0, RSI is 100.
    """
    n = len(close) if close is not None else 0
    if n < period + 1:
        return pd.Series([np.nan] * n, index=close.index if close is not None else None)

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = pd.Series(np.nan, index=close.index, dtype=float)
    avg_loss = pd.Series(np.nan, index=close.index, dtype=float)

    seed_gain = gain.iloc[1 : period + 1].mean()
    seed_loss = loss.iloc[1 : period + 1].mean()
    avg_gain.iloc[period] = seed_gain
    avg_loss.iloc[period] = seed_loss

    for i in range(period + 1, n):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    out = pd.Series(np.nan, index=close.index, dtype=float)
    for i in range(period, n):
        ag = avg_gain.iloc[i]
        al = avg_loss.iloc[i]
        if pd.isna(ag) or pd.isna(al):
            continue
        if ag == 0 and al == 0:
            out.iloc[i] = 50.0
        elif al == 0:
            out.iloc[i] = 100.0
        else:
            rs = ag / al
            out.iloc[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def volume_ratio(volume: pd.Series, period: int = 20) -> float:
    """Today's volume divided by the trailing `period`-bar average volume.

    Excludes today from the denominator so a spike doesn't dilute itself.
    """
    if volume is None or len(volume) < period + 1:
        return float("nan")
    today = float(volume.iloc[-1])
    avg = float(volume.iloc[-(period + 1) : -1].mean())
    if avg <= 0:
        return float("nan")
    return today / avg


def dma_cross(close: pd.Series, fast: int = 50, slow: int = 200) -> bool:
    """True iff the most recent close has fast-DMA strictly above slow-DMA."""
    if close is None or len(close) < slow:
        return False
    fast_ma = sma(close, fast).iloc[-1]
    slow_ma = sma(close, slow).iloc[-1]
    if pd.isna(fast_ma) or pd.isna(slow_ma):
        return False
    return bool(fast_ma > slow_ma)


def below_dma(close: pd.Series, period: int = 50) -> bool:
    if close is None or len(close) < period:
        return False
    ma = sma(close, period).iloc[-1]
    last = close.iloc[-1]
    if pd.isna(ma):
        return False
    return bool(last < ma)
