"""Briefing viewer: today's briefing + history.

Reads `briefings/YYYY-MM-DD-{market}.md` snapshots and renders the most
recent. Implementation of the composer lives in `briefing/composer.py`.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from config.settings import settings


def render() -> None:
    st.subheader("Daily morning briefing")
    today = date.today().isoformat()
    nse_path = settings.briefings_dir / f"{today}-nse.md"
    us_path = settings.briefings_dir / f"{today}-us.md"

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### NSE")
        if nse_path.exists():
            st.markdown(nse_path.read_text())
        else:
            st.info("No NSE briefing yet. Run `python -m briefing.run --date today --market nse`.")
    with col_b:
        st.markdown("### US")
        if us_path.exists():
            st.markdown(us_path.read_text())
        else:
            st.info("No US briefing yet. Run `python -m briefing.run --date today --market us`.")

    st.divider()
    st.markdown("### History")
    snapshots = sorted(settings.briefings_dir.glob("*.md"), reverse=True)
    if not snapshots:
        st.caption("No briefings on disk yet.")
        return
    for p in snapshots[:30]:
        with st.expander(p.name):
            st.markdown(p.read_text())
