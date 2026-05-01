"""1-year backtest of the current rule-set per market.

Walks daily bars from `--start` to `--end` (default: last 252 trading
days). At each bar, evaluates the entry-candidate rules and the
exit rules. Persists every fired signal to `signals_history` with the
real price-at-fire and (when the future window is in-sample) backfills
the 5/20/60-day price columns.

Run:
  python -m scripts.backtest --market us
  python -m scripts.backtest --market nse --lookback-days 365

Output:
  prints a per-rule hit-rate table to stdout
  signals_history rows are written to data/app.db
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

import pandas as pd
import structlog

from config.settings import configure_logging, settings
from data_sources.fundamentals import get_fundamentals_batch
from data_sources.prices import get_history
from data_sources.universe import Market, get_universe
from signals.history import (
    RuleHitRate,
    backfill_subsequent_prices,
    hit_rate_per_rule,
    record_fired_signals,
)
from signals.rules import Signal, evaluate_position

log = structlog.get_logger(__name__)


@dataclass
class BacktestStats:
    market: str
    bars: int
    tickers: int
    signals_recorded: int
    cells_backfilled: int
    hit_rates: list[RuleHitRate]


def _market_enum(raw: str) -> Market:
    raw = raw.lower()
    if raw == "nse":
        return Market.NSE
    if raw == "us":
        return Market.US_COMBINED
    if raw == "nyse":
        return Market.NYSE
    if raw == "nasdaq":
        return Market.NASDAQ
    raise ValueError(f"Unknown market: {raw!r}")


def _slice_history_until(df: pd.DataFrame, on: date) -> pd.DataFrame | None:
    """Return rows with index date <= `on`. None when nothing remains."""
    if df is None or df.empty:
        return None
    try:
        idx_dates = pd.Series(df.index).dt.date
    except AttributeError:
        return None
    mask = idx_dates <= on
    if not mask.any():
        return None
    return df.loc[mask.values]


def _crude_high_since_entry(df: pd.DataFrame) -> float:
    return float(df["Close"].max()) if "Close" in df.columns and len(df) else 0.0


def run(market: Market, *, lookback_days: int = 365) -> BacktestStats:
    universe = get_universe(market)
    if not universe:
        log.warning("backtest_universe_empty", market=str(market))
        return BacktestStats(str(market), 0, 0, 0, 0, [])

    history = get_history(universe, lookback_days=lookback_days + 90)
    fundamentals = get_fundamentals_batch(universe)

    # Sample-size cap for free-tier sanity: limit to first 100 tickers with
    # enough history. Backtest scope can be widened by passing a smaller
    # subset of the universe, or upgrading the feed.
    eligible = [
        (t, history[t.symbol])
        for t in universe
        if history.get(t.symbol) is not None and len(history[t.symbol]) >= 60
    ][:100]

    today = date.today()
    start = today - timedelta(days=lookback_days)

    written = 0
    bars_walked = 0
    seen_keys: set[tuple[str, str, date]] = set()

    for ticker, df in eligible:
        try:
            idx_dates = pd.Series(df.index).dt.date
        except AttributeError:
            continue
        bar_dates = sorted(set(d for d in idx_dates if start <= d <= today))
        bars_walked += len(bar_dates)

        for bar_date in bar_dates:
            sliced = _slice_history_until(df, bar_date)
            if sliced is None or len(sliced) < 60:
                continue
            last_price = float(sliced["Close"].iloc[-1])
            avg_cost = float(sliced["Close"].iloc[0])  # synthetic cost basis at window start
            high_since = _crude_high_since_entry(sliced)

            signals = evaluate_position(
                ticker=ticker.symbol,
                history=sliced,
                avg_cost=avg_cost,
                last_price=last_price,
                high_since_entry=high_since,
                stop_loss_pct=settings.stop_loss_pct,
                profit_target_pct=settings.profit_target_pct,
                trailing_stop_pct=settings.trailing_stop_pct,
                negative_news_24h=0,
            )

            firing: list[Signal] = []
            for sig in signals:
                if not sig.fired or sig.direction == "hold":
                    continue
                key = (sig.ticker, sig.rule, bar_date)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                firing.append(sig)

            if firing:
                ts = datetime.combine(bar_date, datetime.min.time(), tzinfo=timezone.utc)
                written += record_fired_signals(
                    firing, prices={s.ticker: last_price for s in firing}, when=ts,
                )

    backfilled = backfill_subsequent_prices(today, history_by_ticker={t.symbol: df for t, df in eligible})
    rates = hit_rate_per_rule()

    log.info(
        "backtest_complete",
        market=str(market),
        bars=bars_walked,
        tickers=len(eligible),
        signals=written,
        backfilled=backfilled,
    )
    return BacktestStats(
        market=str(market),
        bars=bars_walked,
        tickers=len(eligible),
        signals_recorded=written,
        cells_backfilled=backfilled,
        hit_rates=rates,
    )


def _print_table(stats: BacktestStats) -> None:
    print(f"\nBacktest summary — {stats.market}")
    print(f"  bars walked:        {stats.bars}")
    print(f"  tickers in sample:  {stats.tickers}")
    print(f"  signals recorded:   {stats.signals_recorded}")
    print(f"  follow-up backfill: {stats.cells_backfilled}")
    print()
    if not stats.hit_rates:
        print("  No matured signals to report hit-rate yet.")
        return
    print(f"  {'Rule':<28} {'Dir':<6} {'Horizon':<10} {'N':>6} {'Hits':>6} {'Hit %':>8}")
    print(f"  {'-'*28} {'-'*6} {'-'*10} {'-'*6} {'-'*6} {'-'*8}")
    for r in stats.hit_rates:
        print(
            f"  {r.rule:<28} {r.direction:<6} {r.horizon:<10} "
            f"{r.sample_size:>6d} {r.hits:>6d} {r.hit_rate:>7.1%}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest the current rule-set.")
    parser.add_argument("--market", default="us", choices=["nse", "us", "nyse", "nasdaq"])
    parser.add_argument("--lookback-days", type=int, default=365)
    args = parser.parse_args(argv)

    configure_logging()
    market = _market_enum(args.market)
    stats = run(market, lookback_days=args.lookback_days)
    _print_table(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
