"""Tests for valuation math + FX scaling + portfolio aggregation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from portfolio.valuation import value_portfolio, value_position


@dataclass
class _H:
    ticker: str
    quantity: float
    avg_cost: float
    currency: str
    exchange: str = "US"
    purchase_date: date = date(2025, 1, 1)


def test_value_position_basic_pnl():
    v = value_position(
        ticker="AAPL", quantity=10, avg_cost=100.0, last_price=120.0,
        currency="USD", fx_to_base=1.0,
    )
    assert v.market_value_native == 1200.0
    assert v.market_value_base == 1200.0
    assert v.cost_basis_base == 1000.0
    assert v.pnl_abs_base == 200.0
    assert v.pnl_pct == pytest.approx(0.20)


def test_value_position_fx_scaling_inr_to_usd():
    # 100 shares @ INR 100, current price INR 110, USD/INR ~ 1/83.
    v = value_position(
        ticker="RELIANCE", quantity=100, avg_cost=100.0, last_price=110.0,
        currency="INR", fx_to_base=1 / 83.0,
    )
    assert v.market_value_native == 11000.0
    assert v.market_value_base == pytest.approx(11000.0 / 83.0, rel=1e-6)
    assert v.pnl_pct == pytest.approx(0.10)


def test_value_position_zero_avg_cost_returns_zero_pnl_pct():
    v = value_position(
        ticker="X", quantity=1, avg_cost=0.0, last_price=10.0,
        currency="USD", fx_to_base=1.0,
    )
    assert v.pnl_pct == 0.0


def test_value_portfolio_aggregates_and_weights():
    holdings = [
        _H("AAPL", 10, 100.0, "USD"),
        _H("MSFT", 5, 200.0, "USD"),
    ]
    last_prices = {"AAPL": 150.0, "MSFT": 250.0}
    fx_rates = {"USD": 1.0}
    totals = value_portfolio(holdings, last_prices=last_prices, fx_rates=fx_rates)
    assert totals.total_market_value_base == pytest.approx(1500 + 1250)
    assert totals.total_cost_basis_base == pytest.approx(1000 + 1000)
    assert totals.total_pnl_base == pytest.approx(750)
    weights = {p.ticker: p.weight_in_portfolio for p in totals.positions}
    assert weights["AAPL"] == pytest.approx(1500 / 2750)
    assert weights["MSFT"] == pytest.approx(1250 / 2750)


def test_value_portfolio_handles_missing_price_as_zero():
    holdings = [_H("UNKNOWN", 1, 50.0, "USD")]
    totals = value_portfolio(holdings, last_prices={}, fx_rates={"USD": 1.0})
    assert totals.total_market_value_base == 0.0
