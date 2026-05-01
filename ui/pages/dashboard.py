"""Main dashboard: 3-panel view (screener / news / portfolio).

In v1's first ship, only the screener panel is wired. The news and
portfolio panels render placeholder cards that point at the modules
where their implementations live.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from data_sources.universe import Market
from data_sources.prices import market_is_open
from screener.runner import rank_rows, run as run_screener


_TOP_N_DEFAULT = 50


def _market_options() -> dict[str, Market]:
    return {
        "NSE — Nifty 500 (India)": Market.NSE,
        "NYSE (US)": Market.NYSE,
        "NASDAQ (US)": Market.NASDAQ,
        "US — Combined": Market.US_COMBINED,
    }


def _format_screener_df(rows, top_n: int) -> pd.DataFrame:
    rows = rows[:top_n]
    records = []
    for r in rows:
        pe_display = f"{r.pe:.2f}" if r.pe is not None else "—"
        if r.pe is not None and r.pe_kind == "forward":
            pe_display += " (F)"
        records.append(
            {
                "Ticker": r.symbol,
                "Name": r.name or "",
                "Price": round(r.price, 2) if r.price == r.price else None,
                "P/E": pe_display,
                "Vol Ratio": round(r.volume_ratio, 2) if r.volume_ratio == r.volume_ratio else None,
                "RSI(14)": round(r.rsi, 2) if r.rsi == r.rsi else None,
            }
        )
    return pd.DataFrame.from_records(records)


def render_screener_panel() -> None:
    st.subheader("Screener")

    options = _market_options()
    market_label = st.selectbox(
        "Market",
        list(options.keys()),
        index=0,
        help="Universe is fetched dynamically — no hardcoded tickers.",
    )
    market = options[market_label]

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        ranking = st.radio(
            "Rank by",
            ["Volume Ratio", "Composite"],
            horizontal=True,
            help="Composite = 0.4·VR + 0.3·RSI + 0.3·(1/PE), normalized.",
        )
    with col_b:
        top_n = st.number_input("Show top N", min_value=10, max_value=200, value=_TOP_N_DEFAULT, step=10)
    with col_c:
        watchlist_str = st.text_input(
            "Watchlist additions (comma-separated)",
            help="Tickers added here are always scanned.",
        )

    extra_symbols = tuple(s.strip() for s in watchlist_str.split(",") if s.strip()) if watchlist_str else ()

    open_status = "🟢 open" if market_is_open(str(market.value)) else "🔴 closed"
    st.caption(f"Market status (UTC-naive heuristic): {open_status}")

    if st.button("Run screener", type="primary"):
        with st.spinner("Fetching universe, prices, fundamentals…"):
            result = run_screener(market, extra_symbols=extra_symbols)
        st.session_state["screener_result"] = result

    result = st.session_state.get("screener_result")
    if result is None:
        st.info("Click *Run screener* to scan the selected market.")
        return

    ranked = rank_rows(result.rows, by="composite" if ranking == "Composite" else "volume_ratio")
    st.markdown(
        f"**Scanned:** {result.scanned}  |  **Qualified:** {result.qualified}  |  "
        f"**Generated:** {result.generated_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    df = _format_screener_df(ranked, top_n=int(top_n))
    if df.empty:
        st.warning("No qualifying tickers. Loosen filters or check provider connectivity.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)

    full_csv = result.to_dataframe().to_csv(index=False).encode("utf-8")
    st.download_button(
        "Export full result (CSV)",
        full_csv,
        file_name=f"screener_{market.value}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


def render_news_placeholder() -> None:
    st.subheader("News")
    st.info(
        "News panel ships next milestone — implementation lives in `news/`. "
        "Provider keys go in `.env`."
    )


def render_portfolio_placeholder() -> None:
    st.subheader("Portfolio & Goal")
    st.info(
        "Portfolio panel ships next milestone — implementation lives in `portfolio/` and `goals/`. "
        "CSV schema documented in `README.md`."
    )


def render() -> None:
    tab1, tab2, tab3 = st.tabs(["Screener", "News", "Portfolio & Goal"])
    with tab1:
        render_screener_panel()
    with tab2:
        render_news_placeholder()
    with tab3:
        render_portfolio_placeholder()
