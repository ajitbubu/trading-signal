"""SMTP delivery via Gmail App Password (or any SMTP host).

Failures are logged and swallowed — the briefing on disk is still good,
and the user can resend manually. We never crash the scheduler.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

import structlog

from config.settings import settings

log = structlog.get_logger(__name__)


def _markdown_to_simple_html(markdown: str) -> str:
    """Naive markdown→HTML wrap. Avoids adding a markdown dependency.

    Preserves paragraphs and turns `**bold**` into <strong>. Good enough
    for an email digest; the markdown twin already carries the full
    fidelity content.
    """
    import html
    import re

    escaped = html.escape(markdown)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    paragraphs = escaped.split("\n\n")
    body = "\n".join(f"<p>{p.replace(chr(10), '<br/>')}</p>" for p in paragraphs)
    return f"<html><body style='font-family:sans-serif'>{body}</body></html>"


def send(*, subject: str, body_markdown: str, to: str | None = None) -> bool:
    """Send the briefing as a multipart email. Returns True iff sent."""
    if not settings.smtp_user or not settings.smtp_password:
        log.warning("email_skipped_no_smtp_credentials")
        return False
    recipient = to or settings.briefing_email_to
    if not recipient:
        log.warning("email_skipped_no_recipient")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.briefing_email_from or settings.smtp_user
    message["To"] = recipient
    message.set_content(body_markdown)
    message.add_alternative(_markdown_to_simple_html(body_markdown), subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        log.info("email_sent", subject=subject, recipient=recipient)
        return True
    except Exception as exc:
        log.error("email_send_failed", error=str(exc), recipient=recipient)
        return False
