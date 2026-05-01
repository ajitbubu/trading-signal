"""Signal history ledger: record + backfill + hit-rate."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from signals.rules import Signal


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point the SQLAlchemy engine at a fresh sqlite per test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from config.settings import settings as live_settings
    monkeypatch.setattr(live_settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(live_settings, "data_dir", tmp_path)

    import portfolio.models as models
    monkeypatch.setattr(models, "_engine", None)
    monkeypatch.setattr(models, "_SessionLocal", None)
    yield


def _signal(rule: str, direction: str = "exit", ticker: str = "AAPL", fired: bool = True) -> Signal:
    return Signal(ticker=ticker, direction=direction, rule=rule, detail="x", fired=fired)


def test_record_fired_signals_persists_directional_actions():
    from signals.history import record_fired_signals
    from portfolio.models import SignalRecord, get_session

    sigs = [
        _signal("stop_loss", "exit"),
        _signal("no_rule_fired", "hold"),       # filtered
        _signal("profit_target", "exit", "MSFT"),
    ]
    n = record_fired_signals(sigs, prices={"AAPL": 100.0, "MSFT": 200.0})
    assert n == 2

    with get_session() as s:
        rows = list(s.query(SignalRecord).all())
    assert len(rows) == 2
    rules = {r.rule for r in rows}
    assert rules == {"stop_loss", "profit_target"}


def test_record_skips_unfired_signals():
    from signals.history import record_fired_signals

    sigs = [_signal("stop_loss", "exit", fired=False)]
    assert record_fired_signals(sigs, prices={"AAPL": 100.0}) == 0


def test_record_skips_when_price_missing():
    from signals.history import record_fired_signals

    sigs = [_signal("stop_loss", "exit", "GHOST")]
    assert record_fired_signals(sigs, prices={}) == 0


def test_backfill_fills_5d_when_window_matured():
    from signals.history import backfill_subsequent_prices, record_fired_signals
    from portfolio.models import SignalRecord, get_session

    fire_time = datetime(2026, 4, 1, tzinfo=timezone.utc)
    record_fired_signals(
        [_signal("stop_loss", "exit", "AAA")],
        prices={"AAA": 100.0},
        when=fire_time,
    )

    idx = pd.date_range("2026-04-01", "2026-05-01", freq="D")
    closes = [100.0 + i for i in range(len(idx))]
    df = pd.DataFrame({"Close": closes}, index=idx)

    today = date(2026, 5, 1)
    n = backfill_subsequent_prices(today, history_by_ticker={"AAA": df})
    assert n >= 2  # at least 5d and 20d

    with get_session() as s:
        row = s.query(SignalRecord).first()
    assert row.price_5d is not None
    assert row.price_20d is not None
    assert row.price_5d == pytest.approx(105.0)


def test_hit_rate_computes_per_rule():
    from signals.history import hit_rate_per_rule, record_fired_signals
    from portfolio.models import SignalRecord, get_session

    fire_time = datetime(2026, 4, 1, tzinfo=timezone.utc)
    record_fired_signals(
        [
            _signal("stop_loss", "exit", "DOWN1"),     # hit if drops
            _signal("stop_loss", "exit", "DOWN2"),
            _signal("profit_target", "exit", "UP1"),   # hit if rises
        ],
        prices={"DOWN1": 100.0, "DOWN2": 100.0, "UP1": 100.0},
        when=fire_time,
    )

    with get_session() as s:
        for row in s.query(SignalRecord).all():
            if row.ticker == "DOWN1":
                row.price_20d = 90.0    # -10% → stop_loss hits
            elif row.ticker == "DOWN2":
                row.price_20d = 110.0   # +10% → stop_loss misses
            elif row.ticker == "UP1":
                row.price_20d = 120.0   # +20% → profit_target hits

    rates = hit_rate_per_rule(horizon="price_20d")
    by_rule = {(r.rule, r.direction): r for r in rates}
    assert by_rule[("stop_loss", "exit")].sample_size == 2
    assert by_rule[("stop_loss", "exit")].hits == 1
    assert by_rule[("profit_target", "exit")].hits == 1


def test_hit_rate_skips_unmatured_rows():
    from signals.history import hit_rate_per_rule, record_fired_signals

    fire_time = datetime.now(timezone.utc) - timedelta(days=1)
    record_fired_signals(
        [_signal("stop_loss", "exit", "FRESH")],
        prices={"FRESH": 100.0},
        when=fire_time,
    )
    rates = hit_rate_per_rule(horizon="price_20d")
    # No matured rows → empty list, not an error
    assert rates == []


def test_hit_rate_invalid_horizon_raises():
    from signals.history import hit_rate_per_rule

    with pytest.raises(ValueError):
        hit_rate_per_rule(horizon="bogus")
