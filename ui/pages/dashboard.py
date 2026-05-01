"""Main dashboard: screener + news.

Step 4 ships these two panels end-to-end. Portfolio + goal panels land in
the next session and are intentionally not stubbed in the UI.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from data_sources.prices import market_is_open
from data_sources.rate_limit import log_and_reset_stats, snapshot_stats
from data_sources.universe import Market
from news.aggregator import fetch as fetch_news, filter_items
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


def _render_provider_stats() -> None:
    snap = snapshot_stats()
    if not snap:
        st.caption("Provider stats: no requests yet this cycle.")
        return
    rows = [
        {"Provider": name, "Requests": int(s["requests"]),
         "Cache hits": int(s["cache_hits"]),
         "Effective rps": round(s["effective_rps"], 3)}
        for name, s in snap.items()
    ]
    st.caption("Provider stats (current cycle):")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


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
    st.session_state["selected_market"] = market

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
        log_and_reset_stats()
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

    _render_provider_stats()


def render_news_panel() -> None:
    st.subheader("News")
    market: Market = st.session_state.get("selected_market", Market.NYSE)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        link_to_screener = st.checkbox(
            "Linked to screener results", value=True,
            help="Restrict the feed to tickers currently passing the screen.",
        )
    with col_b:
        sentiment_filter = st.multiselect(
            "Sentiment", ["positive", "neutral", "negative"], default=[],
        )
    with col_c:
        query = st.text_input("Search headlines", value="")

    screener_result = st.session_state.get("screener_result")
    if link_to_screener and screener_result is not None:
        tickers = tuple(r.symbol for r in screener_result.rows if r.qualifies)
    else:
        tickers = ()

    if st.button("Refresh news", type="secondary"):
        with st.spinner("Fetching news…"):
            items = fetch_news(market=str(market.value), tickers=tickers)
        log_and_reset_stats()
        st.session_state["news_items"] = items

    items = st.session_state.get("news_items")
    if not items:
        st.info("Click *Refresh news* to pull from configured providers. "
                "Set `FINNHUB_API_KEY` in `.env` to enable Finnhub.")
        return

    filtered = filter_items(
        items,
        sentiments=tuple(sentiment_filter) if sentiment_filter else (),
        tickers=tickers if link_to_screener else (),
        query=query or None,
    )
    st.caption(f"{len(filtered)} of {len(items)} items match filters.")

    for item in filtered[:50]:
        with st.container():
            sent_badge = {
                "positive": "🟢", "neutral": "⚪", "negative": "🔴",
            }.get(item.sentiment or "neutral", "⚪")
            published_local = item.published_at.astimezone().strftime("%Y-%m-%d %H:%M")
            related = f" — {', '.join(item.related_tickers)}" if item.related_tickers else ""
            st.markdown(
                f"{sent_badge} **[{item.headline}]({item.url})**  \n"
                f"_{item.source} · {published_local}{related}_"
            )
            if item.snippet:
                st.caption(item.snippet[:300] + ("…" if len(item.snippet) > 300 else ""))
            st.divider()

    _render_provider_stats()


def render() -> None:
    tab1, tab2 = st.tabs(["Screener", "News"])
    with tab1:
        render_screener_panel()
    with tab2:
        render_news_panel()
