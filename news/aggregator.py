"""News aggregator: contract module.

`fetch` is the single function the rest of the app calls. Source adapters
live in `news/sources/`. v1 wires Finnhub first, then MarketAux, then
RSS — see implementation sequence in `answers-prefilled.md`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


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
    sources: Sequence[str] = (),
    since: datetime | None = None,
) -> list[NewsItem]:
    """Aggregate news across enabled sources, de-dup, return sorted desc by time.

    Stub: returns empty list until provider adapters land.
    """
    return []
