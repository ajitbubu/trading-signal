"""Finnhub news adapter.

Free tier: 60 calls/min. We rate-limit at 1 rps with burst 5 to stay
comfortably under the cap.

Endpoints used:
  /company-news?symbol=...&from=...&to=...    — ticker-specific news
  /news?category=general                       — general market news

Response shape per item (subset we keep):
  {
    "category": "company news",
    "datetime": 1700000000,
    "headline": "...",
    "id": 12345,
    "image": "...",
    "related": "AAPL",
    "source": "Reuters",
    "summary": "...",
    "url": "..."
  }

`fetch_company_news` and `fetch_market_news` return `list[NewsItem]`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

import httpx
import structlog

from config.settings import settings
from data_sources.rate_limit import RateLimiter, cache_get, cache_set
from news.aggregator import NewsItem
from news.sentiment import classify

log = structlog.get_logger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"
_RATE = RateLimiter(rps=1.0, burst=5)
_TTL = 5 * 60  # CLAUDE.md §5: news list per provider — 5 min


class FinnhubError(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))


def _require_key() -> str:
    key = settings.finnhub_api_key
    if not key:
        raise FinnhubError("FINNHUB_API_KEY not set; skipping Finnhub fetch")
    return key


def _to_news_item(raw: dict) -> NewsItem | None:
    url = raw.get("url")
    headline = raw.get("headline")
    if not url or not headline:
        return None
    ts = raw.get("datetime")
    try:
        published = datetime.fromtimestamp(int(ts), tz=timezone.utc) if ts else datetime.now(timezone.utc)
    except (TypeError, ValueError):
        published = datetime.now(timezone.utc)

    related = raw.get("related") or ""
    related_tickers = [s.strip().upper() for s in str(related).split(",") if s.strip()]

    summary = raw.get("summary") or None
    sentiment_text = f"{headline}\n{summary or ''}"

    return NewsItem(
        url=url,
        headline=headline,
        source=raw.get("source") or "Finnhub",
        published_at=published,
        snippet=summary,
        related_tickers=related_tickers,
        sentiment=classify(sentiment_text, provider_label=None),
        category=raw.get("category"),
    )


def fetch_company_news(
    tickers: Sequence[str],
    *,
    since: datetime | None = None,
) -> list[NewsItem]:
    """Per-ticker news for the last 7 days (or `since`)."""
    if not tickers:
        return []
    try:
        token = _require_key()
    except FinnhubError as exc:
        log.warning("finnhub_skipped", reason=str(exc))
        return []

    since = since or (datetime.now(timezone.utc) - timedelta(days=7))
    to_dt = datetime.now(timezone.utc)
    out: list[NewsItem] = []
    seen_urls: set[str] = set()

    with _client() as client:
        for symbol in tickers:
            cache_key = f"finnhub:company:{symbol}:{since.date()}:{to_dt.date()}"
            cached = cache_get(cache_key)
            if cached is not None:
                items = cached
            else:
                _RATE.acquire()
                try:
                    resp = client.get(
                        f"{_BASE_URL}/company-news",
                        params={
                            "symbol": symbol,
                            "from": since.date().isoformat(),
                            "to": to_dt.date().isoformat(),
                            "token": token,
                        },
                    )
                except httpx.HTTPError as exc:
                    log.warning("finnhub_http_error", symbol=symbol, error=str(exc))
                    continue
                if resp.status_code == 429:
                    log.warning("finnhub_rate_limited", symbol=symbol)
                    continue
                if resp.status_code >= 400:
                    log.warning("finnhub_bad_status", symbol=symbol, status=resp.status_code)
                    continue
                try:
                    items = resp.json() or []
                except ValueError:
                    log.warning("finnhub_bad_json", symbol=symbol)
                    continue
                cache_set(cache_key, items, _TTL)

            for raw in items:
                item = _to_news_item(raw)
                if item is None or item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                out.append(item)

    log.info("finnhub_company_news", tickers=len(tickers), items=len(out))
    return out


def fetch_market_news(category: str = "general") -> list[NewsItem]:
    try:
        token = _require_key()
    except FinnhubError as exc:
        log.warning("finnhub_skipped", reason=str(exc))
        return []

    cache_key = f"finnhub:market:{category}"
    cached = cache_get(cache_key)
    if cached is not None:
        items = cached
    else:
        _RATE.acquire()
        with _client() as client:
            try:
                resp = client.get(
                    f"{_BASE_URL}/news",
                    params={"category": category, "token": token},
                )
            except httpx.HTTPError as exc:
                log.warning("finnhub_http_error", category=category, error=str(exc))
                return []
        if resp.status_code == 429:
            log.warning("finnhub_rate_limited", category=category)
            return []
        if resp.status_code >= 400:
            log.warning("finnhub_bad_status", category=category, status=resp.status_code)
            return []
        try:
            items = resp.json() or []
        except ValueError:
            log.warning("finnhub_bad_json", category=category)
            return []
        cache_set(cache_key, items, _TTL)

    out: list[NewsItem] = []
    seen_urls: set[str] = set()
    for raw in items:
        item = _to_news_item(raw)
        if item is None or item.url in seen_urls:
            continue
        seen_urls.add(item.url)
        out.append(item)

    log.info("finnhub_market_news", category=category, items=len(out))
    return out
