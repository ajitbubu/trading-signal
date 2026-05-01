"""Hit-rate ledger: persist every fired signal and backfill subsequent
5/20/60-day price action so we can report rolling per-rule hit-rate
(answers-prefilled.md §27).

Two write paths:
  - `record_fired_signals(signals, prices, when=None)`: called from any
    code path that evaluates rules (live UI, briefing CLI, backtest).
  - `backfill_subsequent_prices(today, history_by_ticker)`: looks at any
    ledger row whose 5/20/60-day price column is null and the trigger
    is at least N trading days old, then fills the column from the
    provided history.

Read paths:
  - `hit_rate_per_rule(direction='exit', horizon='price_20d')`: rolling
    hit-rate per rule. "Hit" definition depends on direction: an exit
    rule "hits" if the price moved in the rule's intended direction
    (down for stop-loss / trailing-stop / technical-breakdown / negative
    news; up for profit-target). An entry rule "hits" if price is up.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Sequence

import pandas as pd
import structlog
from sqlalchemy import select

from portfolio.models import SignalRecord, get_session
from signals.rules import Signal

log = structlog.get_logger(__name__)

# Rules where "hit" means price went DOWN after the signal fired.
_DOWN_HIT_RULES = {
    "stop_loss",
    "trailing_stop",
    "technical_breakdown",
    "negative_news_cluster",
}
# Rules where "hit" means price went UP after the signal fired.
_UP_HIT_RULES = {
    "profit_target",
}


@dataclass
class RuleHitRate:
    rule: str
    direction: str
    horizon: str
    sample_size: int
    hits: int
    hit_rate: float


def record_fired_signals(
    signals: Sequence[Signal],
    *,
    prices: Mapping[str, float],
    when: datetime | None = None,
) -> int:
    """Persist a batch of fired signals. Returns number written.

    Hold signals are filtered out — the ledger only contains directional
    actions (entry / exit). `prices[ticker]` is the live price at the
    moment the signal fired.
    """
    when = when or datetime.now(timezone.utc)
    written = 0
    with get_session() as s:
        for sig in signals:
            if not sig.fired or sig.direction == "hold":
                continue
            price = prices.get(sig.ticker)
            if price is None:
                log.warning("signal_history_missing_price", ticker=sig.ticker, rule=sig.rule)
                continue
            s.add(
                SignalRecord(
                    ticker=sig.ticker,
                    rule=sig.rule,
                    direction=sig.direction,
                    fired_at=when,
                    price_at_fire=float(price),
                )
            )
            written += 1
    if written:
        log.info("signal_history_recorded", count=written)
    return written


def backfill_subsequent_prices(
    today: date,
    *,
    history_by_ticker: Mapping[str, pd.DataFrame],
) -> int:
    """Fill in 5/20/60-day price columns for ledger rows whose follow-up
    has matured. `history_by_ticker[ticker]['Close']` is consulted by
    date offset.

    Returns the number of cells filled.
    """
    filled = 0
    with get_session() as s:
        rows = list(s.scalars(select(SignalRecord)).all())
        for row in rows:
            df = history_by_ticker.get(row.ticker)
            if df is None or df.empty or "Close" not in df.columns:
                continue
            for col, lookahead_days in (("price_5d", 5), ("price_20d", 20), ("price_60d", 60)):
                if getattr(row, col) is not None:
                    continue
                target_date = row.fired_at.date() + timedelta(days=lookahead_days)
                if target_date > today:
                    continue
                price = _close_at_or_before(df, target_date)
                if price is None:
                    continue
                setattr(row, col, float(price))
                filled += 1
    if filled:
        log.info("signal_history_backfilled", cells=filled)
    return filled


def _close_at_or_before(df: pd.DataFrame, target: date) -> float | None:
    """Return the last close on or before `target`. Indexed-by-date frames
    are normalized to a date series."""
    try:
        idx = df.index
        if hasattr(idx, "tz") and idx.tz is not None:
            idx = idx.tz_convert(None)
        dates = pd.Series(idx).dt.date
        mask = dates <= target
        if not mask.any():
            return None
        last_idx = mask[mask].index[-1]
        return float(df["Close"].iloc[last_idx])
    except Exception:  # pragma: no cover - defensive
        return None


def _is_hit(rule: str, direction: str, price_at_fire: float, future_price: float) -> bool:
    """A signal `hits` if the subsequent price moved in the rule's
    intended direction. Threshold: 1% to ignore noise."""
    if price_at_fire <= 0 or future_price <= 0:
        return False
    move = (future_price - price_at_fire) / price_at_fire
    if rule in _DOWN_HIT_RULES:
        return move <= -0.01
    if rule in _UP_HIT_RULES:
        return move >= 0.01
    if direction == "entry":
        return move >= 0.01
    if direction == "exit":
        return move <= -0.01
    return False


def hit_rate_per_rule(
    *,
    horizon: str = "price_20d",
) -> list[RuleHitRate]:
    """Aggregate hit-rate per rule across all matured ledger rows.

    `horizon` is one of 'price_5d' | 'price_20d' | 'price_60d'.
    """
    if horizon not in {"price_5d", "price_20d", "price_60d"}:
        raise ValueError(f"horizon must be price_5d|price_20d|price_60d, got {horizon!r}")

    with get_session() as s:
        rows = list(s.scalars(select(SignalRecord)).all())

    grouped: dict[tuple[str, str], list[bool]] = {}
    for row in rows:
        future = getattr(row, horizon)
        if future is None:
            continue
        hit = _is_hit(row.rule, row.direction, row.price_at_fire, float(future))
        grouped.setdefault((row.rule, row.direction), []).append(hit)

    out: list[RuleHitRate] = []
    for (rule, direction), hits in sorted(grouped.items()):
        n = len(hits)
        h = sum(1 for x in hits if x)
        out.append(
            RuleHitRate(
                rule=rule,
                direction=direction,
                horizon=horizon,
                sample_size=n,
                hits=h,
                hit_rate=h / n if n else 0.0,
            )
        )
    return out
