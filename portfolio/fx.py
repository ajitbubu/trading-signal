"""USD ↔ INR FX with a fallback ladder.

Primary: yfinance `USDINR=X` (no API key).
Fallback: `https://api.exchangerate.host/latest?base=USD&symbols=INR`
after 3 consecutive yfinance failures (DECISIONS.md D-007 / D-013).

Both paths cache 1h in diskcache. Failures are logged with structlog;
the function always returns a number — if both providers fail, we
return the last cached value or `1.0` for like-currency.
"""
from __future__ import annotations

import threading

import httpx
import structlog

from data_sources.rate_limit import (
    RateLimiter,
    cache_get,
    cache_set,
    record_cache_hit,
    record_request,
)

log = structlog.get_logger(__name__)

_CACHE_KEY_USDINR = "fx:usdinr"
_TTL = 60 * 60  # 1 hour

_yf_limiter = RateLimiter(rps=2.0, burst=4)
_http_limiter = RateLimiter(rps=2.0, burst=4)

_failure_state_lock = threading.Lock()
_yfinance_consecutive_failures = 0
_FAILURES_BEFORE_FALLBACK = 3


def _record_yf_failure() -> None:
    global _yfinance_consecutive_failures
    with _failure_state_lock:
        _yfinance_consecutive_failures += 1


def _reset_yf_failures() -> None:
    global _yfinance_consecutive_failures
    with _failure_state_lock:
        _yfinance_consecutive_failures = 0


def _yfinance_above_failure_threshold() -> bool:
    with _failure_state_lock:
        return _yfinance_consecutive_failures >= _FAILURES_BEFORE_FALLBACK


def _fetch_yfinance() -> float | None:
    try:
        import yfinance as yf

        _yf_limiter.acquire()
        record_request("yfinance_fx")
        ticker = yf.Ticker("USDINR=X")
        info = ticker.fast_info
        rate = float(info.get("last_price") or info.get("lastPrice") or 0.0)
        if rate <= 0:
            return None
        return rate
    except Exception as exc:
        log.warning("yfinance_fx_error", error=str(exc))
        return None


def _fetch_exchangerate_host() -> float | None:
    try:
        _http_limiter.acquire()
        record_request("exchangerate_host")
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
            resp = client.get(
                "https://api.exchangerate.host/latest",
                params={"base": "USD", "symbols": "INR"},
            )
        if resp.status_code != 200:
            log.warning("exchangerate_host_bad_status", status=resp.status_code)
            return None
        data = resp.json() or {}
        rate = float((data.get("rates") or {}).get("INR") or 0.0)
        if rate <= 0:
            return None
        return rate
    except Exception as exc:
        log.warning("exchangerate_host_error", error=str(exc))
        return None


def usd_to_inr() -> float:
    cached = cache_get(_CACHE_KEY_USDINR)
    if cached is not None:
        record_cache_hit("fx")
        return float(cached)

    if not _yfinance_above_failure_threshold():
        rate = _fetch_yfinance()
        if rate is not None:
            _reset_yf_failures()
            cache_set(_CACHE_KEY_USDINR, rate, _TTL)
            return rate
        _record_yf_failure()
        log.warning("yfinance_fx_failed", consecutive=_yfinance_consecutive_failures)

    log.info("fx_fallback_to_exchangerate_host")
    rate = _fetch_exchangerate_host()
    if rate is not None:
        cache_set(_CACHE_KEY_USDINR, rate, _TTL)
        return rate

    log.error("fx_all_providers_failed")
    return float(cached) if cached is not None else 83.0  # last-resort sane default


def fx_rate(from_ccy: str, to_ccy: str) -> float:
    """Multiplier to convert from `from_ccy` to `to_ccy`."""
    f = from_ccy.upper()
    t = to_ccy.upper()
    if f == t:
        return 1.0
    if f == "USD" and t == "INR":
        return usd_to_inr()
    if f == "INR" and t == "USD":
        return 1.0 / usd_to_inr()
    log.warning("fx_unsupported_pair", from_ccy=f, to_ccy=t)
    return 1.0
