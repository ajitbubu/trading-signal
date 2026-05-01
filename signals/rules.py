"""Entry / exit / hold rule engine.

`evaluate_candidate` returns the firing signals for a screener-qualified
ticker (entry).  `evaluate_position` returns the firing signals for a
held position (exit / hold).  Each `Signal` carries the rule that fired
so the UI can surface it (CLAUDE.md §6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from indicators.technical import below_dma, dma_cross, rsi, volume_ratio


Direction = Literal["entry", "exit", "hold"]


@dataclass
class Signal:
    ticker: str
    direction: Direction
    rule: str
    detail: str
    fired: bool


@dataclass
class EntryEvaluation:
    ticker: str
    qualifies: bool                # the three core filters all passed
    tiebreakers: dict[str, bool] = field(default_factory=dict)


def evaluate_candidate(
    *,
    ticker: str,
    history: pd.DataFrame,
    pe: float | None,
    pe_max: float,
    volume_ratio_min: float,
    rsi_period: int,
    rsi_min: float,
    no_earnings_within_days: int | None = None,
    earnings_dates: list[pd.Timestamp] | None = None,
    sentiment_24h: str | None = None,
) -> EntryEvaluation:
    close = history["Close"]
    volume = history["Volume"]

    pe_ok = pe is not None and pe < pe_max
    vr = volume_ratio(volume, period=20)
    vr_ok = pd.notna(vr) and vr > volume_ratio_min
    rsi_last = rsi(close, period=rsi_period).iloc[-1] if len(close) > rsi_period else float("nan")
    rsi_ok = pd.notna(rsi_last) and rsi_last > rsi_min

    qualifies = bool(pe_ok and vr_ok and rsi_ok)

    tiebreakers: dict[str, bool] = {
        "dma_50_above_200": dma_cross(close, 50, 200),
    }
    if no_earnings_within_days is not None and earnings_dates is not None:
        last = history.index[-1] if len(history.index) else pd.Timestamp.utcnow()
        cutoff = last + pd.Timedelta(days=no_earnings_within_days)
        tiebreakers["no_earnings_within_days"] = not any(last <= d <= cutoff for d in earnings_dates)
    if sentiment_24h is not None:
        tiebreakers["non_negative_sentiment_24h"] = sentiment_24h != "negative"

    return EntryEvaluation(ticker=ticker, qualifies=qualifies, tiebreakers=tiebreakers)


def evaluate_position(
    *,
    ticker: str,
    history: pd.DataFrame,
    avg_cost: float,
    last_price: float,
    high_since_entry: float,
    stop_loss_pct: float,
    profit_target_pct: float,
    trailing_stop_pct: float,
    negative_news_24h: int = 0,
) -> list[Signal]:
    """Evaluate a held position. Returns a list of all fired signals.

    A `hold (no_rule_fired)` signal is appended if no exit rule fires,
    so the UI can render the holding without special-casing empty lists.
    """
    out: list[Signal] = []

    if avg_cost > 0:
        change = (last_price - avg_cost) / avg_cost
        if change <= stop_loss_pct:
            out.append(
                Signal(ticker, "exit", "stop_loss",
                       f"{change:.1%} ≤ {stop_loss_pct:.0%} stop", True)
            )
        if change >= profit_target_pct:
            out.append(
                Signal(ticker, "exit", "profit_target",
                       f"{change:.1%} ≥ {profit_target_pct:.0%} target", True)
            )

    if high_since_entry > 0:
        drawdown = (last_price - high_since_entry) / high_since_entry
        if drawdown <= -trailing_stop_pct:
            out.append(
                Signal(
                    ticker, "exit", "trailing_stop",
                    f"{drawdown:.1%} from recent high {high_since_entry:.2f}", True,
                )
            )

    close = history["Close"] if "Close" in history.columns else None
    volume = history["Volume"] if "Volume" in history.columns else None
    if close is not None and volume is not None and below_dma(close, period=50):
        vr = volume_ratio(volume, period=20)
        if pd.notna(vr) and vr >= 1.5:
            out.append(
                Signal(
                    ticker, "exit", "technical_breakdown",
                    f"close < 50-DMA on volume {vr:.2f}× avg", True,
                )
            )

    if negative_news_24h >= 3:
        out.append(
            Signal(
                ticker, "exit", "negative_news_cluster",
                f"{negative_news_24h} negative items in 24h", True,
            )
        )

    if not out:
        out.append(Signal(ticker, "hold", "no_rule_fired", "No entry/exit rule fired", True))
    return out
