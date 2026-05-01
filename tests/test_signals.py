"""Tests for the signal engine: each rule fires; default hold; sizing math."""
from __future__ import annotations

import pandas as pd
import pytest

from signals.rules import evaluate_position
from signals.sizing import size


def _flat_history(n: int = 60, price: float = 100.0, volume: float = 1000.0) -> pd.DataFrame:
    return pd.DataFrame({"Close": [price] * n, "Volume": [volume] * n})


def _decline_history(n: int = 60) -> pd.DataFrame:
    closes = [200.0] * 50 + [180.0, 175.0, 170.0, 168.0, 160.0, 150.0, 140.0, 130.0, 120.0, 100.0]
    volumes = [1000.0] * 50 + [3000.0] * 10
    return pd.DataFrame({"Close": closes, "Volume": volumes})


def test_stop_loss_fires():
    signals = evaluate_position(
        ticker="X",
        history=_flat_history(),
        avg_cost=100.0,
        last_price=90.0,           # -10% < -8% stop
        high_since_entry=110.0,
        stop_loss_pct=-0.08,
        profit_target_pct=0.25,
        trailing_stop_pct=0.10,
    )
    rules_fired = {s.rule for s in signals if s.fired}
    assert "stop_loss" in rules_fired


def test_profit_target_fires():
    signals = evaluate_position(
        ticker="Y",
        history=_flat_history(),
        avg_cost=100.0,
        last_price=130.0,          # +30% ≥ 25% target
        high_since_entry=130.0,
        stop_loss_pct=-0.08,
        profit_target_pct=0.25,
        trailing_stop_pct=0.10,
    )
    rules_fired = {s.rule for s in signals if s.fired}
    assert "profit_target" in rules_fired


def test_trailing_stop_fires():
    signals = evaluate_position(
        ticker="Z",
        history=_flat_history(),
        avg_cost=100.0,
        last_price=108.0,          # 12% below 123 high → trailing stop
        high_since_entry=123.0,
        stop_loss_pct=-0.08,
        profit_target_pct=0.50,
        trailing_stop_pct=0.10,
    )
    rules_fired = {s.rule for s in signals if s.fired}
    assert "trailing_stop" in rules_fired


def test_technical_breakdown_fires_when_below_50dma_on_volume():
    signals = evaluate_position(
        ticker="T",
        history=_decline_history(),
        avg_cost=200.0,
        last_price=100.0,
        high_since_entry=200.0,
        stop_loss_pct=-0.50,        # disabled-ish so we can isolate
        profit_target_pct=2.0,
        trailing_stop_pct=0.99,
    )
    rules_fired = {s.rule for s in signals if s.fired}
    assert "technical_breakdown" in rules_fired


def test_negative_news_cluster_fires_at_three():
    signals = evaluate_position(
        ticker="N",
        history=_flat_history(),
        avg_cost=100.0,
        last_price=100.0,
        high_since_entry=100.0,
        stop_loss_pct=-0.99,
        profit_target_pct=0.99,
        trailing_stop_pct=0.99,
        negative_news_24h=3,
    )
    rules_fired = {s.rule for s in signals if s.fired}
    assert "negative_news_cluster" in rules_fired


def test_no_rule_fires_returns_hold_default():
    signals = evaluate_position(
        ticker="H",
        history=_flat_history(),
        avg_cost=100.0,
        last_price=100.0,
        high_since_entry=100.0,
        stop_loss_pct=-0.99,
        profit_target_pct=0.99,
        trailing_stop_pct=0.99,
        negative_news_24h=0,
    )
    assert len(signals) == 1
    assert signals[0].direction == "hold"
    assert signals[0].rule == "no_rule_fired"


def test_size_basic():
    r = size(portfolio_value=100_000, max_risk_pct=0.02, entry=100.0, stop=92.0)
    # Risk = 2000, per-share risk = 8 → 250 shares
    assert r.shares == 250
    assert r.notional == pytest.approx(25_000.0)
    assert r.risk_amount == pytest.approx(2_000.0)


def test_size_returns_zero_when_entry_le_stop():
    r = size(portfolio_value=100_000, max_risk_pct=0.02, entry=100.0, stop=100.0)
    assert r.shares == 0


def test_size_returns_zero_for_zero_portfolio():
    r = size(portfolio_value=0, max_risk_pct=0.02, entry=100.0, stop=92.0)
    assert r.shares == 0
