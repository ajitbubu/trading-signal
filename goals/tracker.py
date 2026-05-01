"""Goal-tracker math (pure). YTD, gap, required CAGR, feasibility label.

CLAUDE.md §7 spells out the rules. Feasibility labels are blunt by design.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import pow


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
    required_remainder_cagr: float    # annualized
    label: str                        # "On track" | "Stretch" | "Aggressive" | "Highly improbable"


def _trading_days_between(a: date, b: date) -> int:
    """Crude: count weekdays. Sufficient for goal math; tighten with a real
    calendar in v1.1."""
    if b <= a:
        return 0
    days = 0
    cur = a
    while cur < b:
        if cur.weekday() < 5:
            days += 1
        cur = cur.fromordinal(cur.toordinal() + 1)
    return days


def evaluate(
    *,
    starting_capital: float,
    current_value: float,
    target_pct: float,
    start_date: date,
    today: date,
) -> GoalStatus:
    ytd_pct = (current_value - starting_capital) / starting_capital if starting_capital else 0.0
    gap_pct = target_pct - ytd_pct

    elapsed = _trading_days_between(start_date, today)
    year_end = date(start_date.year, 12, 31)
    remaining = max(_trading_days_between(today, year_end), 1)
    fraction_remaining = remaining / _TRADING_DAYS_PER_YEAR

    if 1 + ytd_pct <= 0:
        required_cagr = float("inf")
    else:
        target_value_factor = (1 + target_pct) / (1 + ytd_pct)
        if target_value_factor <= 0 or fraction_remaining <= 0:
            required_cagr = float("inf")
        else:
            required_cagr = pow(target_value_factor, 1.0 / fraction_remaining) - 1.0

    label = _label(required_cagr)
    return GoalStatus(
        starting_capital=starting_capital,
        current_value=current_value,
        target_pct=target_pct,
        start_date=start_date,
        today=today,
        ytd_pct=ytd_pct,
        gap_pct=gap_pct,
        required_remainder_cagr=required_cagr,
        label=label,
    )


def _label(required_cagr: float) -> str:
    if required_cagr <= 0.12:
        return "On track"
    if required_cagr <= 0.25:
        return "Stretch"
    if required_cagr <= 0.50:
        return "Aggressive"
    return "Highly improbable — top decile of historical outcomes"
