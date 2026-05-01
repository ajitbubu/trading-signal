"""Tests for the briefing composer."""
from __future__ import annotations

from datetime import date, datetime, timezone

from briefing.composer import (
    Briefing,
    CalendarEvent,
    DISCLAIMER,
    compose,
    to_json,
    to_markdown,
)
from goals.tracker import evaluate as evaluate_goal
from news.aggregator import NewsItem
from portfolio.valuation import value_portfolio
from signals.rules import Signal


def _holdings_stub():
    from dataclasses import dataclass

    @dataclass
    class _H:
        ticker: str
        quantity: float
        avg_cost: float
        currency: str

    return [_H("AAPL", 10, 100.0, "USD"), _H("MSFT", 5, 200.0, "USD")]


def test_compose_returns_briefing_with_all_sections():
    holdings = _holdings_stub()
    last_prices = {"AAPL": 130.0, "MSFT": 220.0}
    totals = value_portfolio(holdings, last_prices=last_prices, fx_rates={"USD": 1.0})

    goal = evaluate_goal(
        starting_capital=2_000.0,
        current_value=totals.total_market_value_base,
        target_pct=0.50,
        start_date=date(2026, 1, 1),
        today=date(2026, 5, 1),
    )
    news = [
        NewsItem(
            url="https://x.com/1", headline="Apple announces buyback",
            source="Reuters", published_at=datetime(2026, 5, 1, 9, tzinfo=timezone.utc),
            snippet="…", related_tickers=["AAPL"], sentiment="positive", category="corp",
        ),
    ]
    signals = [
        Signal(ticker="AAPL", direction="exit", rule="profit_target",
               detail="+30% ≥ 25%", fired=True),
    ]
    calendar = [CalendarEvent(ticker="AAPL", kind="earnings", when="2026-05-02")]

    briefing = compose(
        market="US",
        today=date(2026, 5, 1),
        goal=goal,
        portfolio_totals=totals,
        signals=signals,
        news=news,
        calendar=calendar,
    )
    assert isinstance(briefing, Briefing)
    assert briefing.market == "US"
    assert briefing.summary
    assert briefing.signals[0].rule == "profit_target"
    assert briefing.movers


def test_to_markdown_contains_seven_sections_and_disclaimer():
    briefing = compose(
        market="US",
        today=date(2026, 5, 1),
        goal=None,
        portfolio_totals=None,
        signals=[],
        news=[],
        calendar=[],
    )
    md = to_markdown(briefing)
    for section in (
        "## Goal status",
        "## Portfolio overnight movement",
        "## Today's calendar",
        "## Today's signals",
        "## News digest",
        "## Risk alerts",
    ):
        assert section in md
    assert DISCLAIMER in md


def test_to_json_round_trips_basic_shape():
    briefing = compose(
        market="US",
        today=date(2026, 5, 1),
        goal=None,
        portfolio_totals=None,
    )
    blob = to_json(briefing)
    assert '"market": "US"' in blob
    assert '"date": "2026-05-01"' in blob


def test_risk_alert_for_concentrated_position():
    holdings = _holdings_stub()
    last_prices = {"AAPL": 1000.0, "MSFT": 50.0}   # AAPL becomes ~99% of portfolio
    totals = value_portfolio(holdings, last_prices=last_prices, fx_rates={"USD": 1.0})
    briefing = compose(
        market="US",
        today=date(2026, 5, 1),
        goal=None,
        portfolio_totals=totals,
    )
    rules = {a.rule for a in briefing.risk_alerts}
    assert "single_position_concentration" in rules
