"""Pure technical-indicator math. No I/O.

The screener and signal engine call into here with a price DataFrame and
get back deterministic numbers that can be unit-tested in isolation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI on a close series.

    Uses the classic Wilder smoothing (exponential with alpha = 1/period).
    """
    if close is None or len(close) < period + 1:
        return pd.Series([np.nan] * len(close), index=close.index)

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.fillna(100.0).where(avg_loss != 0, 100.0)
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
