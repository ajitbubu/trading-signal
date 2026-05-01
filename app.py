"""Streamlit entry point.

Run with: `streamlit run app.py`
"""
from __future__ import annotations

import streamlit as st

from config.settings import configure_logging, ensure_runtime_dirs
from ui.components.layout import page_layout
from ui.pages import dashboard as dashboard_page
from ui.pages import settings_page


def main() -> None:
    ensure_runtime_dirs()
    configure_logging()

    with page_layout("Investment Decision-Support Dashboard"):
        page = st.sidebar.radio(
            "Navigation",
            ["Dashboard", "Settings"],
            index=0,
        )
        if page == "Dashboard":
            dashboard_page.render()
        else:
            settings_page.render()


if __name__ == "__main__":
    main()
