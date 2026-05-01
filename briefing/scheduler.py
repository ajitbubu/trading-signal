"""APScheduler `BackgroundScheduler` running in-process inside Streamlit.

Two cron jobs by default:
  - 08:00 Asia/Kolkata for NSE
  - 07:30 America/New_York for US

Idempotent: `start()` is safe to call multiple times (Streamlit reruns
the script on every interaction). `_started` flag guards re-entry.

When `BRIEFING_COMBINE=true` (DECISIONS.md D-005), one combined job
runs at the earlier wall-clock time. We approximate "earlier" as the
NSE schedule because IST is 9:30h ahead of ET (so 08:00 IST happens
~30m after midnight ET, which is the earliest possible moment we can
publish both markets' briefings before either user starts trading).
"""
from __future__ import annotations

import threading
from datetime import date

import structlog

from config.settings import settings

log = structlog.get_logger(__name__)


_started = False
_lock = threading.Lock()
_scheduler = None


def _run_market(market_value: str) -> None:
    """Job target: write briefing to disk and (if SMTP set) email it."""
    from briefing.run import _market_enum, write_briefing
    from briefing.delivery.email import send

    today = date.today()
    market = _market_enum(market_value)
    artifacts = write_briefing(today, market)
    log.info("scheduled_briefing_written", market=market_value, path=str(artifacts.md_path))

    if settings.smtp_user and settings.smtp_password:
        send(
            subject=f"Briefing — {market.value} — {today.isoformat()}",
            body_markdown=artifacts.md_path.read_text(),
        )


def _run_combined() -> None:
    from briefing.run import _market_enum, write_briefing
    from briefing.delivery.email import send

    today = date.today()
    nse_artifacts = write_briefing(today, _market_enum("nse"))
    us_artifacts = write_briefing(today, _market_enum("us"))
    log.info("scheduled_briefing_combined_written")

    if settings.smtp_user and settings.smtp_password:
        body = nse_artifacts.md_path.read_text() + "\n\n---\n\n" + us_artifacts.md_path.read_text()
        send(
            subject=f"Briefing — Combined — {today.isoformat()}",
            body_markdown=body,
        )


def start() -> bool:
    """Start the scheduler. Returns True iff it newly started."""
    global _started, _scheduler
    with _lock:
        if _started:
            return False
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError as exc:
            log.warning("apscheduler_unavailable", error=str(exc))
            return False

        scheduler = BackgroundScheduler(daemon=True)

        if settings.briefing_combine:
            scheduler.add_job(
                _run_combined,
                trigger=CronTrigger(hour=8, minute=0, timezone="Asia/Kolkata"),
                id="briefing_combined",
                replace_existing=True,
            )
        else:
            scheduler.add_job(
                _run_market,
                args=["NSE"],
                trigger=CronTrigger(hour=8, minute=0, timezone="Asia/Kolkata"),
                id="briefing_nse",
                replace_existing=True,
            )
            scheduler.add_job(
                _run_market,
                args=["US"],
                trigger=CronTrigger(hour=7, minute=30, timezone="America/New_York"),
                id="briefing_us",
                replace_existing=True,
            )

        scheduler.start()
        _scheduler = scheduler
        _started = True
        log.info("briefing_scheduler_started", combine=settings.briefing_combine,
                 jobs=[j.id for j in scheduler.get_jobs()])
        return True


def shutdown() -> None:
    global _started, _scheduler
    with _lock:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
        _scheduler = None
        _started = False
