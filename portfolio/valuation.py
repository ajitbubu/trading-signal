"""Portfolio valuation: market value, P&L, FX. Stub until prices/FX wired."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Valuation:
    ticker: str
    quantity: float
    avg_cost: float
    last_price: float
    currency: str
    market_value_native: float
    market_value_base: float
    pnl_abs_base: float
    pnl_pct: float


def value_position(
    *,
    ticker: str,
    quantity: float,
    avg_cost: float,
    last_price: float,
    currency: str,
    fx_to_base: float,
) -> Valuation:
    mv_native = quantity * last_price
    mv_base = mv_native * fx_to_base
    cost_base = quantity * avg_cost * fx_to_base
    pnl_abs = mv_base - cost_base
    pnl_pct = (last_price - avg_cost) / avg_cost if avg_cost else 0.0
    return Valuation(
        ticker=ticker,
        quantity=quantity,
        avg_cost=avg_cost,
        last_price=last_price,
        currency=currency,
        market_value_native=mv_native,
        market_value_base=mv_base,
        pnl_abs_base=pnl_abs,
        pnl_pct=pnl_pct,
    )
