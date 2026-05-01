"""OHLCV fetcher with caching, batching, and rate limiting.

`yfinance` is the default provider. The function `get_history` returns a
`dict[symbol, DataFrame]` with daily OHLCV bars, indexed by date. The
caller is responsible for indicator math.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

import pandas as pd
import structlog
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from config.settings import settings
from data_sources.rate_limit import RateLimiter, cache_get, cache_set
from data_sources.universe import Ticker

log = structlog.get_logger(__name__)

_yf_limiter = RateLimiter(rps=4.0, burst=8)
_HISTORY_TTL = 30 * 60  # 30 minutes during market hours; ample for daily bars
_QUOTE_TTL = 30  # current price/volume during market hours


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception_type(Exception),
)
def _yf_download(symbols: Sequence[str], period: str, interval: str) -> pd.DataFrame:
    import yfinance as yf

    _yf_limiter.acquire()
    df = yf.download(
        tickers=list(symbols),
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        raise RuntimeError("yfinance returned empty frame")
    return df


def get_history(
    tickers: Sequence[Ticker],
    *,
    lookback_days: int = 60,
) -> dict[str, pd.DataFrame]:
    """Fetch daily OHLCV per ticker over the last `lookback_days` calendar days.

    Returns a dict keyed by `ticker.symbol` (not yf_symbol). Missing/failed
    tickers are absent from the dict.
    """
    if not tickers:
        return {}

    out: dict[str, pd.DataFrame] = {}
    to_fetch: list[Ticker] = []
    for t in tickers:
        cached = cache_get(f"history:{t.yf_symbol}:{lookback_days}")
        if cached is not None:
            out[t.symbol] = cached
        else:
            to_fetch.append(t)

    if not to_fetch:
        return out

    # yfinance handles batches well; cap at 50 to avoid memory spikes.
    batch_size = 50
    period = f"{max(lookback_days, 30)}d"

    for i in range(0, len(to_fetch), batch_size):
        batch = to_fetch[i : i + batch_size]
        yf_symbols = [t.yf_symbol for t in batch]
        try:
            df = _yf_download(yf_symbols, period=period, interval="1d")
        except (RetryError, Exception) as exc:
            log.warning("yf_history_batch_failed", count=len(batch), error=str(exc))
            continue

        for t in batch:
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    sub = df[t.yf_symbol].dropna(how="all")
                else:
                    sub = df.dropna(how="all")
                if sub is None or sub.empty:
                    continue
                sub = sub.rename(columns=str.title)
                out[t.symbol] = sub
                cache_set(f"history:{t.yf_symbol}:{lookback_days}", sub, _HISTORY_TTL)
            except Exception as exc:
                log.warning("yf_history_row_failed", symbol=t.symbol, error=str(exc))
                continue

    log.info("history_fetched", requested=len(tickers), returned=len(out))
    return out


def latest_quote(ticker: Ticker) -> dict[str, float] | None:
    """Return last price and today's volume for a single ticker, or None."""
    key = f"quote:{ticker.yf_symbol}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        import yfinance as yf

        _yf_limiter.acquire()
        info = yf.Ticker(ticker.yf_symbol).fast_info
        out = {
            "price": float(info.get("last_price") or info.get("lastPrice") or 0.0),
            "volume": float(info.get("last_volume") or info.get("lastVolume") or 0.0),
        }
    except Exception as exc:
        log.warning("yf_quote_failed", symbol=ticker.symbol, error=str(exc))
        return None
    cache_set(key, out, _QUOTE_TTL)
    return out


def now_ist_or_et() -> datetime:
    """Used for cache key staleness audits in tests / UI."""
    return datetime.utcnow()


def market_is_open(market_name: str, now: datetime | None = None) -> bool:
    """Cheap calendar check (no holidays). Use a real calendar lib in v1.1."""
    now = now or datetime.utcnow()
    weekday = now.weekday()
    if weekday >= 5:
        return False
    minute = now.hour * 60 + now.minute
    if market_name == "NSE":
        # 03:45 UTC – 10:00 UTC ≈ 09:15 IST – 15:30 IST
        return 225 <= minute <= 600
    if market_name in ("NYSE", "NASDAQ", "US"):
        # 13:30 UTC – 20:00 UTC ≈ 09:30 ET – 16:00 ET
        return 810 <= minute <= 1200
    return False


def _ensure_lookback(_dt: datetime, days: int) -> datetime:
    return _dt - timedelta(days=days)
