"""Tests for email delivery (with mocked SMTP) and scheduler registration."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _smtp_settings(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "alice@example.com")
    monkeypatch.setattr(settings, "smtp_password", "test-pw")
    monkeypatch.setattr(settings, "briefing_email_from", "alice@example.com")
    monkeypatch.setattr(settings, "briefing_email_to", "bob@example.com")


def test_email_send_uses_starttls_login_and_send_message(monkeypatch):
    from briefing.delivery import email as email_mod

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    smtp_factory = MagicMock(return_value=smtp_instance)
    monkeypatch.setattr(email_mod.smtplib, "SMTP", smtp_factory)

    ok = email_mod.send(subject="Test", body_markdown="# Hello\n\n**World**")
    assert ok is True
    smtp_factory.assert_called_once_with("smtp.example.com", 587)
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("alice@example.com", "test-pw")
    smtp_instance.send_message.assert_called_once()
    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message["Subject"] == "Test"
    assert sent_message["To"] == "bob@example.com"


def test_email_skipped_when_no_recipient(monkeypatch):
    from briefing.delivery import email as email_mod
    from config.settings import settings
    monkeypatch.setattr(settings, "briefing_email_to", None)

    ok = email_mod.send(subject="Test", body_markdown="x")
    assert ok is False


def test_email_skipped_when_no_credentials(monkeypatch):
    from briefing.delivery import email as email_mod
    from config.settings import settings
    monkeypatch.setattr(settings, "smtp_user", None)

    ok = email_mod.send(subject="Test", body_markdown="x", to="bob@example.com")
    assert ok is False


def test_email_handles_smtp_error_gracefully(monkeypatch):
    from briefing.delivery import email as email_mod

    def _raise(*_a, **_kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(email_mod.smtplib, "SMTP", _raise)

    ok = email_mod.send(subject="Test", body_markdown="x")
    assert ok is False  # never raises


def test_scheduler_start_is_idempotent(monkeypatch):
    from briefing import scheduler

    scheduler.shutdown()
    fake_jobs: list[tuple] = []

    class _Sched:
        def __init__(self, *a, **kw):
            self._jobs = []
        def add_job(self, *a, **kw):
            self._jobs.append((a, kw))
            fake_jobs.append((a, kw))
        def start(self):
            pass
        def shutdown(self, wait=False):
            pass
        def get_jobs(self):
            return [type("J", (), {"id": kw.get("id")}) for _, kw in self._jobs]

    monkeypatch.setattr(
        "apscheduler.schedulers.background.BackgroundScheduler",
        _Sched,
    )

    started_first = scheduler.start()
    started_second = scheduler.start()
    assert started_first is True
    assert started_second is False
    scheduler.shutdown()
    # Two jobs registered (NSE + US) since BRIEFING_COMBINE is False by default.
    assert len(fake_jobs) == 2
