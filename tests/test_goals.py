"""Goal-tracker math: YTD, gap, required CAGR, feasibility labels.

The label thresholds are blunt by design (answers-prefilled.md §28).
"""
from __future__ import annotations

from datetime import date
from math import isfinite

import pytest

from goals.tracker import evaluate, structural_tension_warning


def test_on_track_when_ahead_of_target():
    status = evaluate(
        starting_capital=100_000.0,
        current_value=160_000.0,                   # YTD +60% > target 50%
        target_pct=0.50,
        start_date=date(2026, 1, 1),
        today=date(2026, 6, 1),
    )
    assert status.ytd_pct == pytest.approx(0.60)
    assert status.gap_pct == pytest.approx(-0.10)
    assert isfinite(status.required_remainder_cagr)
    assert status.required_remainder_cagr < 0
    assert status.label == "On track"


def test_aggressive_when_modestly_behind():
    # YTD +25%, target +50%, mid-year → required CAGR ≈ 36% → Aggressive bucket
    status = evaluate(
        starting_capital=100_000.0,
        current_value=125_000.0,
        target_pct=0.50,
        start_date=date(2026, 1, 1),
        today=date(2026, 6, 1),
    )
    assert status.label == "Aggressive"
    assert 0.25 < status.required_remainder_cagr <= 0.50


def test_highly_improbable_label_emerges():
    status = evaluate(
        starting_capital=100_000.0,
        current_value=80_000.0,                    # YTD -20%, target 50%, late
        target_pct=0.50,
        start_date=date(2026, 1, 1),
        today=date(2026, 11, 1),
    )
    assert status.label.startswith("Highly improbable")


def test_year_end_returns_inf_required_cagr():
    status = evaluate(
        starting_capital=100_000.0,
        current_value=100_000.0,
        target_pct=0.50,
        start_date=date(2026, 1, 1),
        today=date(2026, 12, 31),                  # no trading days remain
    )
    assert status.required_remainder_cagr == float("inf")
    assert status.label.startswith("Highly improbable")


def test_negative_ytd_below_minus_100_marked_impossible():
    status = evaluate(
        starting_capital=100_000.0,
        current_value=-1.0,                        # impossible scenario, total loss
        target_pct=0.50,
        start_date=date(2026, 1, 1),
        today=date(2026, 6, 1),
    )
    assert status.required_remainder_cagr == float("inf")


def test_structural_tension_warning_fires_for_default_combo():
    # 50% target + 2% per-trade risk should warn (answers §22).
    msg = structural_tension_warning(0.50, 0.02)
    assert msg is not None
    assert "50%" in msg


def test_structural_tension_warning_silent_for_modest_target():
    msg = structural_tension_warning(0.10, 0.02)
    assert msg is None
