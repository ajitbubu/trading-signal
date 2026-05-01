"""Shared Streamlit layout: header, sidebar, footer.

Pages call `with page_layout(title): ...` to inherit the standard chrome.
"""
from __future__ import annotations

from contextlib import contextmanager

import streamlit as st

from ui.components.disclaimer import render_footer


def render_header(title: str) -> None:
    st.set_page_config(
        page_title="Investment Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title(title)


@contextmanager
def page_layout(title: str):
    render_header(title)
    try:
        yield
    finally:
        render_footer()
