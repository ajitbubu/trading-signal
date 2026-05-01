"""In-app briefing renderer (Streamlit)."""
from __future__ import annotations

import streamlit as st

from briefing.composer import Briefing, to_markdown


def render(briefing: Briefing) -> None:
    st.markdown(to_markdown(briefing))
