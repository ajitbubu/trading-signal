"""Briefing composer: pure function over the dashboard's snapshot data.

CLAUDE.md §8 fixes the section order:
  1. Plain-English summary (one line)
  2. Goal status
  3. Portfolio overnight movement
  4. Today's calendar
  5. Today's signals
  6. News digest
  7. Risk alerts

`compose` takes already-collected inputs (no I/O) so the function is
trivial to unit-test.  `to_markdown` and `to_json` serialise.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Sequence

from goals.tracker import GoalStatus
from news.aggregator import NewsItem
from portfolio.valuation import PortfolioTotals, Valuation
from signals.rules import Signal


DISCLAIMER = (
    "Informational only. Not investment advice. "
    "You are responsible for your own trades."
)


@dataclass
class CalendarEvent:
    ticker: str
    kind: str        # "earnings" | "ex_dividend" | "macro" | "rebalance"
    when: str        # ISO date or "today"
    detail: str = ""


@dataclass
class RiskAlert:
    severity: str    # "info" | "warning" | "critical"
    rule: str
    detail: str


@dataclass
class Briefing:
    date: date
    market: str       # "NSE" | "US"
    summary: str
    goal: GoalStatus | None
    portfolio_totals: PortfolioTotals | None
    movers: list[Valuation] = field(default_factory=list)
    calendar: list[CalendarEvent] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)
    risk_alerts: list[RiskAlert] = field(default_factory=list)


def _summary_line(
    market: str,
    goal: GoalStatus | None,
    totals: PortfolioTotals | None,
    signal_count: int,
) -> str:
    parts: list[str] = [f"{market} briefing"]
    if goal is not None:
        parts.append(
            f"YTD {goal.ytd_pct:+.1%} vs target {goal.target_pct:+.0%} "
            f"({goal.label.split('—')[0].strip()})"
        )
    if totals is not None:
        parts.append(f"portfolio value {totals.total_market_value_base:,.0f}")
    if signal_count:
        parts.append(f"{signal_count} active signals")
    return "; ".join(parts) + "."


def _top_movers(positions: Sequence[Valuation], limit: int = 5) -> list[Valuation]:
    return sorted(positions, key=lambda v: abs(v.pnl_pct), reverse=True)[:limit]


def _risk_alerts(
    totals: PortfolioTotals | None,
    *,
    concentration_threshold: float = 0.20,
    drawdown_threshold: float = -0.10,
) -> list[RiskAlert]:
    alerts: list[RiskAlert] = []
    if totals is None:
        return alerts
    for v in totals.positions:
        if v.weight_in_portfolio > concentration_threshold:
            alerts.append(
                RiskAlert(
                    severity="warning",
                    rule="single_position_concentration",
                    detail=f"{v.ticker} is {v.weight_in_portfolio:.1%} of portfolio "
                    f"(> {concentration_threshold:.0%})",
                )
            )
        if v.pnl_pct <= drawdown_threshold:
            alerts.append(
                RiskAlert(
                    severity="warning",
                    rule="position_drawdown",
                    detail=f"{v.ticker} drawdown {v.pnl_pct:.1%}",
                )
            )
    if totals.total_pnl_pct <= drawdown_threshold:
        alerts.append(
            RiskAlert(
                severity="critical",
                rule="portfolio_drawdown",
                detail=f"total P&L {totals.total_pnl_pct:.1%}",
            )
        )
    return alerts


def compose(
    *,
    market: str,
    today: date,
    goal: GoalStatus | None,
    portfolio_totals: PortfolioTotals | None,
    signals: Sequence[Signal] = (),
    news: Sequence[NewsItem] = (),
    calendar: Sequence[CalendarEvent] = (),
) -> Briefing:
    movers = _top_movers(portfolio_totals.positions) if portfolio_totals else []
    risk_alerts = _risk_alerts(portfolio_totals)
    summary = _summary_line(market, goal, portfolio_totals, len([s for s in signals if s.fired]))
    return Briefing(
        date=today,
        market=market,
        summary=summary,
        goal=goal,
        portfolio_totals=portfolio_totals,
        movers=list(movers),
        calendar=list(calendar),
        signals=list(signals),
        news=list(news)[:20],
        risk_alerts=risk_alerts,
    )


def to_markdown(b: Briefing) -> str:
    lines: list[str] = []
    lines.append(f"# Morning briefing — {b.market} — {b.date.isoformat()}")
    lines.append("")
    lines.append(b.summary)
    lines.append("")

    lines.append("## Goal status")
    if b.goal:
        lines.append(f"- YTD: **{b.goal.ytd_pct:+.2%}**")
        lines.append(f"- Gap to target: **{b.goal.gap_pct:+.2%}**")
        lines.append(f"- Required remainder CAGR: **{b.goal.required_remainder_cagr:+.2%}**")
        lines.append(f"- Feasibility: **{b.goal.label}**")
    else:
        lines.append("_Set base capital and target on the Portfolio page to enable goal tracking._")
    lines.append("")

    lines.append("## Portfolio overnight movement")
    if b.portfolio_totals:
        t = b.portfolio_totals
        lines.append(
            f"- Market value: **{t.total_market_value_base:,.2f}**  "
            f"(P&L {t.total_pnl_base:+,.2f} / {t.total_pnl_pct:+.2%})"
        )
        if b.movers:
            lines.append("- Top movers (by absolute P&L %):")
            for v in b.movers:
                lines.append(f"  - {v.ticker}: {v.pnl_pct:+.2%} ({v.pnl_abs_base:+,.2f})")
    else:
        lines.append("_No holdings yet. Import a CSV on the Portfolio page._")
    lines.append("")

    lines.append("## Today's calendar")
    if b.calendar:
        for e in b.calendar:
            lines.append(f"- {e.when}: {e.ticker} — {e.kind} {e.detail}".rstrip())
    else:
        lines.append("_No calendar events available._")
    lines.append("")

    lines.append("## Today's signals")
    if b.signals:
        for s in b.signals:
            lines.append(f"- **{s.direction.upper()}** · {s.ticker} · `{s.rule}` — {s.detail}")
    else:
        lines.append("_No signals fired._")
    lines.append("")

    lines.append("## News digest")
    if b.news:
        for item in b.news[:10]:
            sent_icon = {"positive": "🟢", "neutral": "⚪", "negative": "🔴"}.get(
                item.sentiment or "neutral", "⚪"
            )
            published = item.published_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"- {sent_icon} [{item.headline}]({item.url}) — _{item.source}, {published}_")
    else:
        lines.append("_No news fetched._")
    lines.append("")

    lines.append("## Risk alerts")
    if b.risk_alerts:
        for a in b.risk_alerts:
            lines.append(f"- **{a.severity.upper()}** · `{a.rule}` — {a.detail}")
    else:
        lines.append("_No risk alerts._")
    lines.append("")

    lines.append("---")
    lines.append(f"_{DISCLAIMER}_")
    return "\n".join(lines)


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"unserialisable: {type(value).__name__}")


def to_json(b: Briefing) -> str:
    return json.dumps(asdict(b), default=_json_default, indent=2)
