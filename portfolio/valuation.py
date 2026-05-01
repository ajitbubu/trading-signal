"""Portfolio valuation: market value, P&L, FX-converted totals.

Pure functions: callers pass last_prices and FX rates in. The UI layer
fetches those via `data_sources.prices.latest_quote` and `portfolio.fx`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass
class Valuation:
    ticker: str
    quantity: float
    avg_cost: float
    last_price: float
    currency: str
    market_value_native: float
    market_value_base: float
    cost_basis_base: float
    pnl_abs_base: float
    pnl_pct: float
    weight_in_portfolio: float = 0.0


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
        cost_basis_base=cost_base,
        pnl_abs_base=pnl_abs,
        pnl_pct=pnl_pct,
    )


@dataclass
class PortfolioTotals:
    total_market_value_base: float
    total_cost_basis_base: float
    total_pnl_base: float
    total_pnl_pct: float
    positions: list[Valuation]


def value_portfolio(
    holdings: Iterable,
    *,
    last_prices: Mapping[str, float],
    fx_rates: Mapping[str, float],
    base_currency: str = "USD",
) -> PortfolioTotals:
    """Aggregate holdings into a `PortfolioTotals` snapshot.

    `holdings` is any iterable of objects exposing
    `ticker, quantity, avg_cost, currency` (matches both `HoldingRow`
    from the importer and `Holding` from the SQLAlchemy model).
    `last_prices[ticker]` is in the holding's native currency.
    `fx_rates[currency]` is the multiplier to convert that currency to
    `base_currency`. Missing prices/rates default to 0/1 with a logged
    warning at the caller — this function does no I/O.
    """
    valuations: list[Valuation] = []
    for h in holdings:
        last_price = float(last_prices.get(h.ticker, 0.0))
        fx_to_base = float(fx_rates.get(h.currency, 1.0))
        valuations.append(
            value_position(
                ticker=h.ticker,
                quantity=float(h.quantity),
                avg_cost=float(h.avg_cost),
                last_price=last_price,
                currency=h.currency,
                fx_to_base=fx_to_base,
            )
        )

    total_mv = sum(v.market_value_base for v in valuations)
    total_cost = sum(v.cost_basis_base for v in valuations)
    total_pnl = total_mv - total_cost
    pnl_pct = (total_pnl / total_cost) if total_cost else 0.0

    if total_mv > 0:
        for v in valuations:
            v.weight_in_portfolio = v.market_value_base / total_mv

    return PortfolioTotals(
        total_market_value_base=total_mv,
        total_cost_basis_base=total_cost,
        total_pnl_base=total_pnl,
        total_pnl_pct=pnl_pct,
        positions=valuations,
    )
