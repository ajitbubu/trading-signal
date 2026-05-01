"""Goal-tracker math (pure). YTD, gap, required CAGR, feasibility label.

CLAUDE.md §7 spells out the rules. Feasibility labels are blunt by design
(answers-prefilled.md §28 — no softening).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite, pow


_TRADING_DAYS_PER_YEAR = 252


@dataclass
class GoalStatus:
    starting_capital: float
    current_value: float
    target_pct: float                 # e.g. 0.50
    start_date: date
    today: date
    ytd_pct: float
    gap_pct: float
    required_remainder_cagr: float    # annualized (math.inf when impossible)
    label: str


def _trading_days_between(a: date, b: date) -> int:
    if b <= a:
        return 0
    days = 0
    cur = a
    while cur < b:
        if cur.weekday() < 5:
            days += 1
        cur = cur + timedelta(days=1)
    return days


def _label_for_cagr(required_cagr: float) -> str:
    if not isfinite(required_cagr):
        return "Highly improbable — top decile of historical outcomes"
    if required_cagr <= 0.12:
        return "On track"
    if required_cagr <= 0.25:
        return "Stretch"
    if required_cagr <= 0.50:
        return "Aggressive"
    return "Highly improbable — top decile of historical outcomes"


def evaluate(
    *,
    starting_capital: float,
    current_value: float,
    target_pct: float,
    start_date: date,
    today: date,
) -> GoalStatus:
    if starting_capital <= 0:
        ytd_pct = 0.0
    else:
        ytd_pct = (current_value - starting_capital) / starting_capital

    gap_pct = target_pct - ytd_pct

    year_end = date(start_date.year, 12, 31)
    remaining = _trading_days_between(today, year_end)
    fraction_remaining = remaining / _TRADING_DAYS_PER_YEAR

    if 1 + ytd_pct <= 0 or fraction_remaining <= 0:
        required_cagr = float("inf")
    else:
        target_value_factor = (1 + target_pct) / (1 + ytd_pct)
        if target_value_factor <= 0:
            required_cagr = float("inf")
        else:
            required_cagr = pow(target_value_factor, 1.0 / fraction_remaining) - 1.0

    return GoalStatus(
        starting_capital=starting_capital,
        current_value=current_value,
        target_pct=target_pct,
        start_date=start_date,
        today=today,
        ytd_pct=ytd_pct,
        gap_pct=gap_pct,
        required_remainder_cagr=required_cagr,
        label=_label_for_cagr(required_cagr),
    )


def structural_tension_warning(target_pct: float, max_risk_pct: float) -> str | None:
    """Return a warning string when the goal is structurally hard to reach
    given the per-trade risk cap (answers-prefilled.md §22). Else None.
    """
    if target_pct >= 0.40 and max_risk_pct <= 0.025:
        return (
            f"Structural tension: a {target_pct:.0%} annual target with "
            f"{max_risk_pct:.1%} risk per trade implies a high signal hit-rate "
            f"and large average winners. Consider whether your edge supports it."
        )
    return None
