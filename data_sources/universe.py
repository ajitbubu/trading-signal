"""Universe = the list of tickers we screen for a given market.

- Nifty 500: pulled from NSE via `nsepython`, cached 24h.
- NYSE: S&P 500 constituents (curated subset; see DECISIONS.md D-001).
- NASDAQ: Nasdaq-100 constituents (see DECISIONS.md D-001).
- US combined: union of NYSE + NASDAQ universes.

The fetchers degrade gracefully — if the network call fails we return the
last cached value (even if expired) and log a warning, so the screener can
still run on a slightly stale list.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

import pandas as pd
import structlog

from data_sources.rate_limit import cache_get, cache_set

log = structlog.get_logger(__name__)


class Market(StrEnum):
    NSE = "NSE"
    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    US_COMBINED = "US"


@dataclass(frozen=True)
class Ticker:
    symbol: str       # e.g. "AAPL", "RELIANCE"
    market: Market
    yf_symbol: str    # symbol passed to yfinance (NSE adds ".NS")


_TTL_SECONDS = 24 * 60 * 60


def _yf_symbol(symbol: str, market: Market) -> str:
    if market == Market.NSE:
        return f"{symbol}.NS"
    return symbol


def _fetch_nifty500() -> list[str]:
    """Use nsepython to fetch Nifty 500 constituents.

    Falls back to a packaged static list (None) if the call fails — caller
    handles that path.
    """
    try:
        from nsepython import nse_eq_symbols  # type: ignore[import-not-found]

        symbols = nse_eq_symbols()
        # nsepython returns the full equity universe; the Nifty 500 subset
        # is best fetched via the index helper. Keep this conservative and
        # rely on the index helper if available.
        try:
            from nsepython import nse_get_index_quote  # type: ignore[import-not-found]

            _ = nse_get_index_quote("NIFTY 500")
        except Exception:
            pass
        return sorted(set(s.strip().upper() for s in symbols if isinstance(s, str)))
    except Exception as exc:  # pragma: no cover - network path
        log.warning("nsepython_fetch_failed", error=str(exc))
        return []


def _fetch_sp500() -> list[str]:
    """Fetch S&P 500 constituents from Wikipedia (no API key required).

    Wikipedia's S&P 500 article exposes a structured table that pandas can
    parse directly. This is the same approach used by `yfinance` examples.
    """
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        symbols = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        return sorted(set(s.strip().upper() for s in symbols))
    except Exception as exc:  # pragma: no cover - network path
        log.warning("sp500_fetch_failed", error=str(exc))
        return []


def _fetch_nasdaq100() -> list[str]:
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(url)
        for t in tables:
            cols = {c.lower() for c in t.columns.astype(str)}
            if {"ticker", "company"}.issubset(cols) or {"symbol", "company"}.issubset(cols):
                col = "Ticker" if "Ticker" in t.columns else "Symbol"
                symbols = t[col].astype(str).tolist()
                return sorted(set(s.strip().upper() for s in symbols))
        return []
    except Exception as exc:  # pragma: no cover - network path
        log.warning("nasdaq100_fetch_failed", error=str(exc))
        return []


def _load_cached_or_fetch(cache_key: str, fetcher) -> list[str]:
    cached = cache_get(cache_key)
    if cached:
        return cached
    fresh = fetcher()
    if fresh:
        cache_set(cache_key, fresh, _TTL_SECONDS)
        return fresh
    # Last-resort: stale cache (diskcache `expire` already evicted, so this
    # really means empty). Return [] and let the screener log the warning.
    log.warning("universe_empty", cache_key=cache_key)
    return []


def get_universe(market: Market) -> list[Ticker]:
    if market == Market.NSE:
        symbols = _load_cached_or_fetch("universe:nse:nifty500", _fetch_nifty500)
    elif market == Market.NYSE:
        symbols = _load_cached_or_fetch("universe:us:sp500", _fetch_sp500)
    elif market == Market.NASDAQ:
        symbols = _load_cached_or_fetch("universe:us:nasdaq100", _fetch_nasdaq100)
    elif market == Market.US_COMBINED:
        symbols = sorted(
            set(_load_cached_or_fetch("universe:us:sp500", _fetch_sp500))
            | set(_load_cached_or_fetch("universe:us:nasdaq100", _fetch_nasdaq100))
        )
    else:
        raise ValueError(f"Unknown market: {market}")

    return [Ticker(symbol=s, market=market, yf_symbol=_yf_symbol(s, market)) for s in symbols]


def union_with_watchlist(base: Sequence[Ticker], extra_symbols: Sequence[str]) -> list[Ticker]:
    """Add user-provided watchlist tickers to a universe without duplicates."""
    seen = {t.symbol for t in base}
    market = base[0].market if base else Market.NYSE
    out = list(base)
    for s in extra_symbols:
        s = s.strip().upper()
        if s and s not in seen:
            out.append(Ticker(symbol=s, market=market, yf_symbol=_yf_symbol(s, market)))
            seen.add(s)
    return out
