"""Finnhub adapter tests with mocked HTTP — no network access."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "finnhub_api_key", "test-key")


def _mock_response(payload, status_code: int = 200):
    class _Resp:
        def __init__(self):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    return _Resp()


def test_company_news_parses_payload(monkeypatch):
    from news.sources import finnhub
    from data_sources import rate_limit as rl

    rl._cache.clear()  # ensure no stale cache from prior runs

    sample = [
        {
            "category": "company",
            "datetime": 1700000000,
            "headline": "Apple posts record quarter",
            "id": 1,
            "related": "AAPL",
            "source": "Reuters",
            "summary": "Strong iPhone sales drove the beat.",
            "url": "https://example.com/apple-1",
        },
        {  # missing url → skipped
            "datetime": 1700000100,
            "headline": "No URL",
            "related": "AAPL",
            "source": "Wire",
        },
    ]

    class _StubClient:
        def __init__(self, *_a, **_kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False
        def get(self, _url, params=None):
            return _mock_response(sample)

    monkeypatch.setattr(finnhub, "_client", lambda: _StubClient())

    items = finnhub.fetch_company_news(["AAPL"], since=datetime(2023, 11, 1, tzinfo=timezone.utc))
    assert len(items) == 1
    assert items[0].url == "https://example.com/apple-1"
    assert items[0].source == "Reuters"
    assert items[0].related_tickers == ["AAPL"]
    assert items[0].sentiment in {"positive", "neutral", "negative"}


def test_company_news_handles_429(monkeypatch):
    from news.sources import finnhub
    from data_sources import rate_limit as rl

    rl._cache.clear()

    class _StubClient:
        def __init__(self, *_a, **_kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False
        def get(self, _url, params=None):
            return _mock_response([], status_code=429)

    monkeypatch.setattr(finnhub, "_client", lambda: _StubClient())

    items = finnhub.fetch_company_news(["AAPL"])
    assert items == []


def test_market_news_dedupes_within_response(monkeypatch):
    from news.sources import finnhub
    from data_sources import rate_limit as rl

    rl._cache.clear()

    sample = [
        {"datetime": 1700000000, "headline": "A", "url": "https://x.com/1",
         "source": "S", "summary": "", "related": ""},
        {"datetime": 1700000005, "headline": "A", "url": "https://x.com/1",
         "source": "S", "summary": "", "related": ""},  # same URL → drop
        {"datetime": 1700000010, "headline": "B", "url": "https://x.com/2",
         "source": "S", "summary": "", "related": ""},
    ]

    class _StubClient:
        def __init__(self, *_a, **_kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False
        def get(self, _url, params=None):
            return _mock_response(sample)

    monkeypatch.setattr(finnhub, "_client", lambda: _StubClient())

    items = finnhub.fetch_market_news("general")
    urls = [i.url for i in items]
    assert urls == ["https://x.com/1", "https://x.com/2"]


def test_skips_when_api_key_missing(monkeypatch):
    from config.settings import settings
    from news.sources import finnhub

    monkeypatch.setattr(settings, "finnhub_api_key", None)
    assert finnhub.fetch_market_news() == []
    assert finnhub.fetch_company_news(["AAPL"]) == []
