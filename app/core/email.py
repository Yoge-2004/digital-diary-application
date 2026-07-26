"""Minimal transactional email sending, using only the standard library.

If SMTP isn't configured (no smtp_host), the message is logged instead of
sent — convenient for local development, but be aware that in that mode
anyone who can read the server's logs can read a password-reset link.
Configure real SMTP before this ever handles real user accounts.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger("app.email")


def send_email(smtp_settings, to_email: str, subject: str, body: str) -> None:
    if not smtp_settings.smtp_host:
        logger.warning(
            "SMTP not configured (SMTP_HOST unset) - logging email instead of sending.\n"
            "To: %s\nSubject: %s\n%s",
            to_email, subject, body,
        )
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_settings.smtp_from
    msg["To"] = to_email

    with smtplib.SMTP(smtp_settings.smtp_host, smtp_settings.smtp_port, timeout=10) as server:
        if smtp_settings.smtp_use_tls:
            server.starttls()
        if smtp_settings.smtp_user:
            server.login(smtp_settings.smtp_user, smtp_settings.smtp_password)
        server.sendmail(smtp_settings.smtp_from, [to_email], msg.as_string())


def send_password_reset_email(smtp_settings, to_email: str, reset_url: str) -> None:
    subject = "Reset your Digital Diary password"
    body = (
        "We received a request to reset your Digital Diary password.\n\n"
        f"Reset it here (valid for 1 hour): {reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email — "
        "your password won't be changed."
    )
    send_email(smtp_settings, to_email, subject, body)
