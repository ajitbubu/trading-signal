"""De-duplicate news items by URL exact match, then by headline similarity.

Uses `rapidfuzz` token-set ratio. Threshold default is 90, configurable.
"""
from __future__ import annotations

from typing import Iterable

from rapidfuzz import fuzz

from news.aggregator import NewsItem


def dedupe(items: Iterable[NewsItem], headline_threshold: int = 90) -> list[NewsItem]:
    seen_urls: set[str] = set()
    kept: list[NewsItem] = []
    for item in items:
        if item.url in seen_urls:
            continue
        if any(
            fuzz.token_set_ratio(item.headline, k.headline) >= headline_threshold for k in kept
        ):
            continue
        seen_urls.add(item.url)
        kept.append(item)
    return kept
