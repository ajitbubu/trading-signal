"""Position sizing helper.

position_size = (portfolio_value * max_risk_pct) / (entry - stop)
Pure math. No opinions.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SizingResult:
    shares: int
    notional: float
    risk_amount: float


def size(
    *,
    portfolio_value: float,
    max_risk_pct: float,
    entry: float,
    stop: float,
) -> SizingResult:
    if entry <= 0 or stop <= 0 or entry <= stop:
        return SizingResult(shares=0, notional=0.0, risk_amount=0.0)
    risk_amount = portfolio_value * max_risk_pct
    per_share_risk = entry - stop
    raw_shares = risk_amount / per_share_risk
    shares = max(int(raw_shares), 0)
    return SizingResult(
        shares=shares,
        notional=shares * entry,
        risk_amount=shares * per_share_risk,
    )
