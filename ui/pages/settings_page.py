"""Settings page: rules, schedule, providers.

For v1, settings are read from `config/rules_default.yaml` and the values
shown here are read-only. Persistence to the `settings` SQLite table lands
with the portfolio milestone.
"""
from __future__ import annotations

import yaml
import streamlit as st

from config.settings import settings


def render() -> None:
    st.subheader("Settings")

    st.markdown("#### Provider keys (read-only)")
    st.caption("Configured via `.env`. Restart the app after changes.")
    keys = {
        "Finnhub": bool(settings.finnhub_api_key),
        "MarketAux": bool(settings.marketaux_api_key),
        "GNews": bool(settings.gnews_api_key),
        "Alpha Vantage": bool(settings.alphavantage_api_key),
        "Anthropic (AI summaries)": bool(settings.anthropic_api_key),
        "SMTP": bool(settings.smtp_user and settings.smtp_password),
    }
    for name, present in keys.items():
        st.write(f"- {name}: {'✅' if present else '⚠️ missing'}")

    st.markdown("#### Active rules (read-only — edit `config/rules_default.yaml`)")
    rules_path = settings.root / "config" / "rules_default.yaml"
    if rules_path.exists():
        st.code(yaml.safe_dump(yaml.safe_load(rules_path.read_text()), sort_keys=False), language="yaml")
    else:
        st.warning("Rules file missing.")

    st.markdown("#### Refresh cadence")
    st.write(f"- Price refresh: every {settings.price_refresh_seconds}s")
    st.write(f"- News refresh: every {settings.news_refresh_seconds}s")

    st.markdown("#### AI summaries")
    st.write(f"- Enabled: {settings.enable_ai_summaries}")
    st.write(f"- Model: {settings.anthropic_model}")
