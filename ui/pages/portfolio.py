"""Portfolio page: CSV upload, manual add, holdings table, goal panel.

Goal panel is co-located here per CLAUDE.md §1 (the goal sits with the
portfolio).
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from config.settings import settings
from data_sources.prices import latest_quote
from data_sources.universe import Market, Ticker
from goals.tracker import evaluate as evaluate_goal, structural_tension_warning
from portfolio.fx import fx_rate
from portfolio.importer import HoldingRow, parse_csv, template_csv
from portfolio.models import Holding, get_session, get_user_setting, set_user_setting
from portfolio.valuation import value_portfolio


def _persist_holdings(rows: list[HoldingRow], replace: bool) -> int:
    with get_session() as s:
        if replace:
            s.query(Holding).delete()
        for r in rows:
            s.add(
                Holding(
                    ticker=r.ticker,
                    exchange=r.exchange,
                    quantity=r.quantity,
                    avg_cost=r.avg_cost,
                    purchase_date=r.purchase_date,
                    currency=r.currency,
                )
            )
        return len(rows)


def _load_holdings() -> list[Holding]:
    with get_session() as s:
        return list(s.query(Holding).all())


def _value_holdings(holdings: list[Holding]):
    last_prices: dict[str, float] = {}
    for h in holdings:
        yf_symbol = f"{h.ticker}.NS" if h.exchange == "NSE" else h.ticker
        market = Market.NSE if h.exchange == "NSE" else Market.NYSE
        quote = latest_quote(Ticker(symbol=h.ticker, market=market, yf_symbol=yf_symbol))
        last_prices[h.ticker] = float(quote["price"]) if quote else float(h.avg_cost)
    fx_rates = {ccy: fx_rate(ccy, "USD") for ccy in {h.currency for h in holdings}}
    return value_portfolio(holdings, last_prices=last_prices, fx_rates=fx_rates, base_currency="USD")


def _render_import_section() -> None:
    st.markdown("#### Import holdings")
    cola, colb = st.columns(2)
    with cola:
        uploaded = st.file_uploader(
            "Upload CSV (canonical schema or Fidelity export)",
            type=["csv"],
        )
    with colb:
        replace = st.checkbox("Replace existing holdings on import", value=True)
        st.download_button(
            "Download canonical-schema template",
            template_csv(),
            file_name="holdings_template.csv",
            mime="text/csv",
        )

    if uploaded is not None and st.button("Save uploaded CSV", type="primary"):
        try:
            text = uploaded.getvalue().decode("utf-8")
            rows = parse_csv(text)
            saved = _persist_holdings(rows, replace=replace)
            st.success(f"Imported {saved} holdings.")
        except ValueError as exc:
            st.error(f"Import failed: {exc}")


def _render_manual_add() -> None:
    with st.expander("Manual add"):
        with st.form("manual_add_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                ticker = st.text_input("Ticker").strip().upper()
                exchange = st.selectbox("Exchange", ["NYSE", "NASDAQ", "NSE", "US"])
            with c2:
                qty = st.number_input("Quantity", min_value=0.0, step=1.0)
                avg_cost = st.number_input("Avg cost (per share)", min_value=0.0, step=0.01)
            with c3:
                purchase_date = st.date_input("Purchase date", value=date(date.today().year, 1, 1))
                currency = st.selectbox("Currency", ["USD", "INR"])
            submitted = st.form_submit_button("Add holding")
            if submitted and ticker and qty > 0:
                _persist_holdings(
                    [HoldingRow(ticker, exchange, qty, avg_cost, purchase_date, currency)],
                    replace=False,
                )
                st.success(f"Added {ticker}.")


def _render_holdings_table(holdings: list[Holding]) -> None:
    if not holdings:
        st.info("No holdings yet. Upload a CSV or add one manually.")
        return
    totals = _value_holdings(holdings)
    rows = [
        {
            "Ticker": v.ticker,
            "Qty": round(v.quantity, 4),
            "Avg cost": round(v.avg_cost, 2),
            "Last": round(v.last_price, 2),
            "Mkt val (USD)": round(v.market_value_base, 2),
            "P&L (USD)": round(v.pnl_abs_base, 2),
            "P&L %": f"{v.pnl_pct:+.2%}",
            "Weight": f"{v.weight_in_portfolio:.2%}",
            "Ccy": v.currency,
        }
        for v in totals.positions
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.markdown(
        f"**Total value:** ${totals.total_market_value_base:,.2f}  |  "
        f"**Cost basis:** ${totals.total_cost_basis_base:,.2f}  |  "
        f"**P&L:** ${totals.total_pnl_base:,.2f} ({totals.total_pnl_pct:+.2%})"
    )
    st.session_state["portfolio_totals"] = totals


def _render_goal_panel() -> None:
    st.markdown("#### Goal tracking")

    raw_capital = get_user_setting("starting_capital_usd")
    raw_target = get_user_setting("annual_target_pct", str(settings.annual_target_pct))
    raw_start = get_user_setting("goal_start_date", date(date.today().year, 1, 1).isoformat())

    c1, c2, c3 = st.columns(3)
    with c1:
        starting_capital = st.number_input(
            "Starting capital (USD)",
            min_value=0.0,
            step=1000.0,
            value=float(raw_capital) if raw_capital else 0.0,
        )
    with c2:
        target_pct = st.number_input(
            "Annual target (%)",
            min_value=0.0,
            max_value=500.0,
            value=float(raw_target) * 100 if raw_target else settings.annual_target_pct * 100,
            step=5.0,
        ) / 100.0
    with c3:
        start_date = st.date_input(
            "Goal start date",
            value=date.fromisoformat(raw_start) if raw_start else date(date.today().year, 1, 1),
        )

    if st.button("Save goal settings"):
        set_user_setting("starting_capital_usd", str(starting_capital))
        set_user_setting("annual_target_pct", str(target_pct))
        set_user_setting("goal_start_date", start_date.isoformat())
        st.success("Saved.")

    totals = st.session_state.get("portfolio_totals")
    if totals is None or starting_capital <= 0:
        st.info("Save a starting capital and (re)load the holdings table to compute goal status.")
        return

    status = evaluate_goal(
        starting_capital=starting_capital,
        current_value=totals.total_market_value_base,
        target_pct=target_pct,
        start_date=start_date,
        today=date.today(),
    )
    a, b, c, d = st.columns(4)
    a.metric("YTD", f"{status.ytd_pct:+.2%}")
    b.metric("Gap", f"{status.gap_pct:+.2%}")
    cagr_display = "n/a" if status.required_remainder_cagr == float("inf") else f"{status.required_remainder_cagr:+.2%}"
    c.metric("Req. CAGR", cagr_display)
    d.metric("Feasibility", status.label.split("—")[0].strip())

    with st.expander("Math behind the label"):
        st.markdown(
            f"""
- Current value: **${status.current_value:,.2f}**
- Starting capital: **${status.starting_capital:,.2f}**
- YTD return = (current − start) / start = **{status.ytd_pct:+.4%}**
- Gap to target = target − YTD = **{status.gap_pct:+.4%}**
- Required remainder CAGR = **{cagr_display}**
- Label rule: ≤ 12% → On track; ≤ 25% → Stretch; ≤ 50% → Aggressive; > 50% → Highly improbable
            """
        )

    warning = structural_tension_warning(target_pct, settings.max_risk_per_trade_pct)
    if warning:
        st.warning(warning)


def render() -> None:
    st.subheader("Portfolio & Goal")
    _render_import_section()
    _render_manual_add()
    holdings = _load_holdings()
    _render_holdings_table(holdings)
    st.divider()
    _render_goal_panel()
