"""Briefing viewer: today's briefings + history."""
from __future__ import annotations

import subprocess
import sys
from datetime import date

import streamlit as st

from config.settings import settings


def _run_briefing(market: str) -> tuple[bool, str]:
    """Invoke `python -m briefing.run --date today --market <market>`.
    Returns (ok, output)."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "briefing.run", "--date", "today", "--market", market],
            capture_output=True, text=True, timeout=180, check=False,
        )
        return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def _read_or_placeholder(p) -> str:
    if p.exists():
        return p.read_text()
    return f"_No briefing yet at `{p.name}`. Click the generate button._"


def render() -> None:
    st.subheader("Daily morning briefing")
    today_iso = date.today().isoformat()
    nse_path = settings.briefings_dir / f"{today_iso}-nse.md"
    us_path = settings.briefings_dir / f"{today_iso}-us.md"

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### NSE")
        if st.button("Generate NSE briefing now", key="run_nse"):
            ok, out = _run_briefing("nse")
            (st.success if ok else st.error)(out or ("done" if ok else "failed"))
        st.markdown(_read_or_placeholder(nse_path))
    with c2:
        st.markdown("### US")
        if st.button("Generate US briefing now", key="run_us"):
            ok, out = _run_briefing("us")
            (st.success if ok else st.error)(out or ("done" if ok else "failed"))
        st.markdown(_read_or_placeholder(us_path))

    st.divider()
    st.markdown("### History")
    snapshots = sorted(settings.briefings_dir.glob("*.md"), reverse=True)
    if not snapshots:
        st.caption("No briefings on disk yet.")
        return
    for p in snapshots[:30]:
        with st.expander(p.name):
            st.markdown(p.read_text())
