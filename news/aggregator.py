"""News aggregator: dispatches to enabled source adapters, dedupes, sorts.

In v1 only Finnhub is wired. MarketAux + RSS land in a follow-up.
The dispatcher pattern keeps this module honest: every source returns a
`list[NewsItem]` and aggregator merges them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence


@dataclass
class NewsItem:
    url: str
    headline: str
    source: str
    published_at: datetime
    snippet: str | None
    related_tickers: list[str]
    sentiment: str | None         # "positive" | "neutral" | "negative" | None
    category: str | None          # "earnings" | "macro" | ... | None


def fetch(
    market: str,
    tickers: Sequence[str] = (),
    sources: Sequence[str] = ("finnhub",),
    since: datetime | None = None,
) -> list[NewsItem]:
    """Aggregate news across enabled sources, de-dupe, return sorted desc by time.

    `market` is one of "NSE" | "NYSE" | "NASDAQ" | "US". For Finnhub the
    market only affects which `category` we pass to the general-news
    endpoint (US uses "general"; NSE has no first-party Finnhub coverage,
    so we only pull ticker-specific news for held/qualified NSE tickers).
    """
    # Imported lazily so test envs without network can stub the source.
    from news.dedupe import dedupe
    from news.sources import finnhub

    since = since or (datetime.now(timezone.utc) - timedelta(hours=24))
    items: list[NewsItem] = []

    if "finnhub" in sources:
        items.extend(finnhub.fetch_market_news("general"))
        if tickers:
            items.extend(finnhub.fetch_company_news(tickers, since=since))

    items = dedupe(items)
    items = [i for i in items if i.published_at >= since]
    items.sort(key=lambda i: i.published_at, reverse=True)
    return items


def filter_items(
    items: Sequence[NewsItem],
    *,
    sources: Sequence[str] = (),
    sentiments: Sequence[str] = (),
    tickers: Sequence[str] = (),
    query: str | None = None,
) -> list[NewsItem]:
    out: list[NewsItem] = []
    for item in items:
        if sources and item.source not in sources:
            continue
        if sentiments and (item.sentiment or "neutral") not in sentiments:
            continue
        if tickers and not any(t in item.related_tickers for t in tickers):
            continue
        if query:
            q = query.lower()
            blob = f"{item.headline} {item.snippet or ''}".lower()
            if q not in blob:
                continue
        out.append(item)
    return out
