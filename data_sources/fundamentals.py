"""Fundamentals: P/E (trailing primary, forward fallback), name, sector.

Cached for 1 hour because P/E recomputes on every earnings or price tick
but our screener tolerates an hour of staleness.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import structlog

from data_sources.rate_limit import RateLimiter, cache_get, cache_set
from data_sources.universe import Ticker

log = structlog.get_logger(__name__)

_yf_limiter = RateLimiter(rps=4.0, burst=8)
_TTL = 60 * 60


@dataclass
class Fundamentals:
    symbol: str
    name: str | None
    sector: str | None
    pe_trailing: float | None
    pe_forward: float | None
    pe_used: float | None       # the value we'll filter on
    pe_used_kind: str | None    # "trailing" | "forward" | None


def _pick_pe(trailing: float | None, forward: float | None) -> tuple[float | None, str | None]:
    if trailing is not None and trailing > 0:
        return trailing, "trailing"
    if forward is not None and forward > 0:
        return forward, "forward"
    return None, None


def get_fundamentals(ticker: Ticker) -> Fundamentals | None:
    key = f"fundamentals:{ticker.yf_symbol}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    try:
        import yfinance as yf

        _yf_limiter.acquire()
        info = yf.Ticker(ticker.yf_symbol).get_info()
    except Exception as exc:
        log.warning("yf_fundamentals_failed", symbol=ticker.symbol, error=str(exc))
        return None

    if not info:
        return None

    trailing = info.get("trailingPE")
    forward = info.get("forwardPE")
    used, used_kind = _pick_pe(trailing, forward)
    out = Fundamentals(
        symbol=ticker.symbol,
        name=info.get("shortName") or info.get("longName"),
        sector=info.get("sector"),
        pe_trailing=trailing if isinstance(trailing, (int, float)) else None,
        pe_forward=forward if isinstance(forward, (int, float)) else None,
        pe_used=used,
        pe_used_kind=used_kind,
    )
    cache_set(key, out, _TTL)
    return out


def get_fundamentals_batch(tickers: Sequence[Ticker]) -> dict[str, Fundamentals]:
    out: dict[str, Fundamentals] = {}
    for t in tickers:
        f = get_fundamentals(t)
        if f is not None:
            out[t.symbol] = f
    return out
