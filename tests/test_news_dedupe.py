"""News dedupe tests: URL exact match + headline fuzzy match."""
from __future__ import annotations

from datetime import datetime, timezone

from news.aggregator import NewsItem
from news.dedupe import dedupe


def _item(url: str, headline: str) -> NewsItem:
    return NewsItem(
        url=url,
        headline=headline,
        source="TestWire",
        published_at=datetime.now(timezone.utc),
        snippet=None,
        related_tickers=[],
        sentiment="neutral",
        category=None,
    )


def test_dedupes_exact_url_duplicates():
    items = [
        _item("https://x.com/a", "Alpha rises"),
        _item("https://x.com/a", "Alpha rises"),
        _item("https://x.com/b", "Beta moves"),
    ]
    out = dedupe(items)
    assert [i.url for i in out] == ["https://x.com/a", "https://x.com/b"]


def test_dedupes_near_duplicate_headlines():
    items = [
        _item("https://x.com/a", "Apple beats earnings expectations"),
        _item("https://y.com/b", "Apple Beats Earnings Expectations"),  # case + URL diff
        _item("https://z.com/c", "Tesla announces new factory"),
    ]
    out = dedupe(items, headline_threshold=90)
    assert len(out) == 2
    assert out[0].url == "https://x.com/a"
    assert out[1].url == "https://z.com/c"


def test_does_not_dedupe_different_headlines():
    items = [
        _item("https://x.com/a", "Apple beats earnings"),
        _item("https://y.com/b", "Tesla launches Cybertruck"),
        _item("https://z.com/c", "Fed raises rates"),
    ]
    out = dedupe(items, headline_threshold=90)
    assert len(out) == 3
