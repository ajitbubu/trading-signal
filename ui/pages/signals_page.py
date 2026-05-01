"""Signals page: per-position signal cards + sizing calculator.

Reuses any screener result already present in `st.session_state` so the
user doesn't pay another data-fetch round-trip when navigating from the
dashboard.
"""
from __future__ import annotations

import streamlit as st

from config.settings import settings
from data_sources.prices import get_history
from data_sources.universe import Market, Ticker
from portfolio.models import Holding, get_session
from signals.history import hit_rate_per_rule, record_fired_signals
from signals.rules import evaluate_position
from signals.sizing import size as size_position


def _load_holdings() -> list[Holding]:
    with get_session() as s:
        return list(s.query(Holding).all())


def _render_position_signals() -> None:
    st.markdown("#### Position signals")
    holdings = _load_holdings()
    if not holdings:
        st.info("No holdings — import on the Portfolio page first.")
        return

    yf_tickers = [
        Ticker(
            symbol=h.ticker,
            market=Market.NSE if h.exchange == "NSE" else Market.NYSE,
            yf_symbol=f"{h.ticker}.NS" if h.exchange == "NSE" else h.ticker,
        )
        for h in holdings
    ]
    histories = get_history(yf_tickers, lookback_days=60)

    persist = st.checkbox(
        "Persist fired signals to history (for hit-rate tracking)",
        value=False,
        help="Adds rows to signals_history. Disable to evaluate without writing.",
    )

    fired_for_persistence = []
    fired_prices: dict[str, float] = {}

    for h in holdings:
        df = histories.get(h.ticker)
        if df is None or df.empty:
            st.warning(f"{h.ticker}: no history available; skipping.")
            continue
        last_price = float(df["Close"].iloc[-1])
        high_since = float(h.high_since_entry) if h.high_since_entry else float(df["Close"].max())
        signals = evaluate_position(
            ticker=h.ticker,
            history=df,
            avg_cost=float(h.avg_cost),
            last_price=last_price,
            high_since_entry=high_since,
            stop_loss_pct=float(h.stop_loss_pct) if h.stop_loss_pct is not None else settings.stop_loss_pct,
            profit_target_pct=float(h.profit_target_pct) if h.profit_target_pct is not None else settings.profit_target_pct,
            trailing_stop_pct=float(h.trailing_stop_pct) if h.trailing_stop_pct is not None else settings.trailing_stop_pct,
        )

        with st.container():
            badge_color = {
                "exit": "🔴",
                "entry": "🟢",
                "hold": "⚪",
            }
            for s in signals:
                st.markdown(
                    f"{badge_color.get(s.direction, '⚪')} **{s.ticker}** · "
                    f"`{s.direction}/{s.rule}` — {s.detail}"
                )
                if persist and s.fired and s.direction != "hold":
                    fired_for_persistence.append(s)
                    fired_prices[s.ticker] = last_price
            st.caption(
                f"avg cost {h.avg_cost:.2f} · last {last_price:.2f} · "
                f"high since entry {high_since:.2f}"
            )
            st.divider()

    if fired_for_persistence:
        n = record_fired_signals(fired_for_persistence, prices=fired_prices)
        st.success(f"Persisted {n} fired signals to history.")


def _render_hit_rate_panel() -> None:
    st.markdown("#### Hit-rate per rule (rolling)")
    horizon = st.selectbox(
        "Horizon",
        ["price_5d", "price_20d", "price_60d"],
        index=1,
        help="Hit-rate over the next N trading days after the signal fired.",
    )
    rates = hit_rate_per_rule(horizon=horizon)
    if not rates:
        st.info(
            "No matured signals yet. Run `python -m scripts.backtest --market us` "
            "or persist live signals (checkbox above) to populate."
        )
        return

    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "Rule": r.rule,
                "Direction": r.direction,
                "N": r.sample_size,
                "Hits": r.hits,
                "Hit %": f"{r.hit_rate:.1%}",
            }
            for r in rates
        ]
    )
    st.dataframe(df, hide_index=True, use_container_width=True)


def _render_sizing() -> None:
    st.markdown("#### Position sizing")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        portfolio_value = st.number_input("Portfolio value (USD)", min_value=0.0, step=1000.0, value=100_000.0)
    with c2:
        max_risk_pct = st.number_input(
            "Max risk per trade (%)", min_value=0.1, max_value=10.0, step=0.1,
            value=settings.max_risk_per_trade_pct * 100,
        ) / 100.0
    with c3:
        entry = st.number_input("Entry price", min_value=0.0, step=0.01, value=100.0)
    with c4:
        stop = st.number_input("Stop price", min_value=0.0, step=0.01, value=92.0)

    result = size_position(
        portfolio_value=portfolio_value,
        max_risk_pct=max_risk_pct,
        entry=entry,
        stop=stop,
    )
    a, b, c = st.columns(3)
    a.metric("Shares", f"{result.shares:,}")
    b.metric("Notional (USD)", f"${result.notional:,.2f}")
    c.metric("Risk amount (USD)", f"${result.risk_amount:,.2f}")


def render() -> None:
    st.subheader("Signals & Sizing")
    _render_position_signals()
    st.divider()
    _render_hit_rate_panel()
    st.divider()
    _render_sizing()
