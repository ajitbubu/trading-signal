"""Persistent footer disclaimer.

Per CLAUDE.md §10, the disclaimer is non-removable. It is wired into the
layout helper, not behind a config flag.
"""
from __future__ import annotations

import streamlit as st

DISCLAIMER_TEXT = (
    "**Informational only. Not investment advice. "
    "You are responsible for your own trades.**"
)


def render_footer() -> None:
    st.divider()
    st.caption(DISCLAIMER_TEXT)
