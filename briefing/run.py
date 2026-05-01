"""CLI entry point: `python -m briefing.run --date today --market nse|us`.

Loads holdings from SQLite, runs the screener, fetches news, evaluates the
goal, composes the briefing, writes it to `briefings/{date}-{market}.{md,json}`,
and (if SMTP is configured) emails it.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

import structlog

from config.settings import configure_logging, ensure_runtime_dirs, settings
from data_sources.universe import Market

log = structlog.get_logger(__name__)


def _resolve_date(value: str) -> date:
    if value == "today":
        return date.today()
    return date.fromisoformat(value)


def _market_enum(value: str) -> Market:
    value = value.lower()
    if value == "nse":
        return Market.NSE
    if value == "us":
        return Market.US_COMBINED
    if value == "nyse":
        return Market.NYSE
    if value == "nasdaq":
        return Market.NASDAQ
    raise ValueError(f"Unknown market: {value!r}")


def _load_holdings():
    from portfolio.models import Holding, get_session

    with get_session() as s:
        return list(s.query(Holding).all())


def _load_goal_inputs(holdings_total_value: float):
    from goals.tracker import evaluate
    from portfolio.models import get_user_setting

    raw_capital = get_user_setting("starting_capital_usd")
    raw_target = get_user_setting("annual_target_pct")
    raw_start = get_user_setting("goal_start_date")

    if raw_capital is None:
        return None

    try:
        starting_capital = float(raw_capital)
        target_pct = float(raw_target) if raw_target else settings.annual_target_pct
        start_date = date.fromisoformat(raw_start) if raw_start else date(date.today().year, 1, 1)
    except ValueError:
        log.warning("goal_settings_corrupt", capital=raw_capital, target=raw_target, start=raw_start)
        return None

    return evaluate(
        starting_capital=starting_capital,
        current_value=holdings_total_value,
        target_pct=target_pct,
        start_date=start_date,
        today=date.today(),
    )


def _value_holdings(holdings):
    from data_sources.prices import latest_quote
    from data_sources.universe import Ticker
    from portfolio.fx import fx_rate
    from portfolio.valuation import value_portfolio

    last_prices: dict[str, float] = {}
    for h in holdings:
        yf_symbol = f"{h.ticker}.NS" if h.exchange == "NSE" else h.ticker
        quote = latest_quote(Ticker(symbol=h.ticker, market=Market.NSE if h.exchange == "NSE" else Market.NYSE, yf_symbol=yf_symbol))
        last_prices[h.ticker] = float(quote["price"]) if quote else float(h.avg_cost)

    currencies = {h.currency for h in holdings}
    fx_rates = {ccy: fx_rate(ccy, "USD") for ccy in currencies}
    return value_portfolio(holdings, last_prices=last_prices, fx_rates=fx_rates, base_currency="USD")


def _fetch_news_and_signals(holdings, market: Market):
    from news.aggregator import fetch as fetch_news
    from data_sources.prices import get_history
    from data_sources.universe import Ticker
    from signals.history import record_fired_signals
    from signals.rules import evaluate_position

    held_tickers = tuple(h.ticker for h in holdings)
    news_items = fetch_news(market=str(market.value), tickers=held_tickers)

    held_yf_tickers = [
        Ticker(
            symbol=h.ticker,
            market=Market.NSE if h.exchange == "NSE" else Market.NYSE,
            yf_symbol=f"{h.ticker}.NS" if h.exchange == "NSE" else h.ticker,
        )
        for h in holdings
    ]
    histories = get_history(held_yf_tickers, lookback_days=60) if held_yf_tickers else {}

    negative_24h_by_ticker: dict[str, int] = {}
    cutoff = datetime.now(timezone.utc).timestamp() - 24 * 3600
    for item in news_items:
        if item.sentiment != "negative":
            continue
        if item.published_at.timestamp() < cutoff:
            continue
        for tkr in item.related_tickers:
            negative_24h_by_ticker[tkr] = negative_24h_by_ticker.get(tkr, 0) + 1

    signals = []
    for h in holdings:
        df = histories.get(h.ticker)
        if df is None or df.empty:
            continue
        last_price = float(df["Close"].iloc[-1])
        high_since = float(h.high_since_entry) if h.high_since_entry else float(df["Close"].max())
        signals.extend(
            evaluate_position(
                ticker=h.ticker,
                history=df,
                avg_cost=float(h.avg_cost),
                last_price=last_price,
                high_since_entry=high_since,
                stop_loss_pct=float(h.stop_loss_pct) if h.stop_loss_pct is not None else settings.stop_loss_pct,
                profit_target_pct=float(h.profit_target_pct) if h.profit_target_pct is not None else settings.profit_target_pct,
                trailing_stop_pct=float(h.trailing_stop_pct) if h.trailing_stop_pct is not None else settings.trailing_stop_pct,
                negative_news_24h=negative_24h_by_ticker.get(h.ticker, 0),
            )
        )

    fired_prices = {}
    fired = []
    for sig in signals:
        if not sig.fired or sig.direction == "hold":
            continue
        df = histories.get(sig.ticker)
        if df is None or df.empty:
            continue
        fired_prices[sig.ticker] = float(df["Close"].iloc[-1])
        fired.append(sig)
    if fired:
        record_fired_signals(fired, prices=fired_prices)

    return news_items, signals


@dataclass
class BriefingArtifacts:
    md_path: Path
    json_path: Path


def write_briefing(today: date, market: Market) -> BriefingArtifacts:
    from briefing.composer import compose, to_json, to_markdown

    ensure_runtime_dirs()
    holdings = _load_holdings()
    totals = _value_holdings(holdings) if holdings else None
    goal = _load_goal_inputs(totals.total_market_value_base if totals else 0.0)
    news_items, signals = _fetch_news_and_signals(holdings, market)

    briefing = compose(
        market=str(market.value),
        today=today,
        goal=goal,
        portfolio_totals=totals,
        signals=signals,
        news=news_items,
    )

    market_slug = "nse" if market == Market.NSE else "us"
    md_path = settings.briefings_dir / f"{today.isoformat()}-{market_slug}.md"
    json_path = settings.briefings_dir / f"{today.isoformat()}-{market_slug}.json"

    md_path.write_text(to_markdown(briefing))
    json_path.write_text(to_json(briefing))

    log.info("briefing_written", market=market_slug, md=str(md_path), json=str(json_path))
    return BriefingArtifacts(md_path=md_path, json_path=json_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a morning briefing.")
    parser.add_argument("--date", default="today")
    parser.add_argument("--market", default="us", choices=["nse", "us", "nyse", "nasdaq"])
    parser.add_argument("--email", action="store_true", help="Also send via SMTP if configured.")
    args = parser.parse_args(argv)

    configure_logging()
    today = _resolve_date(args.date)
    market = _market_enum(args.market)

    artifacts = write_briefing(today, market)
    print(f"Wrote {artifacts.md_path}")

    if args.email and settings.smtp_user and settings.smtp_password:
        from briefing.delivery.email import send

        try:
            send_md = artifacts.md_path.read_text()
            send(
                subject=f"Briefing — {market.value} — {today.isoformat()}",
                body_markdown=send_md,
            )
            print(f"Email sent to {settings.briefing_email_to}")
        except Exception as exc:
            log.error("briefing_email_failed", error=str(exc))
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
