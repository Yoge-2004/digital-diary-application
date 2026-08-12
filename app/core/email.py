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


def send_password_reset_email(smtp_settings, to_email: str, code: str) -> None:
    subject = "Your Digital Diary password reset code"
    body = (
        "We received a request to reset your Digital Diary password.\n\n"
        f"Your verification code is: {code}\n\n"
        "Enter this code on the reset password page to choose a new password. "
        "It's valid for 15 minutes and can only be used once.\n\n"
        "If you didn't request this, you can safely ignore this email — "
        "your password won't be changed."
    )
    send_email(smtp_settings, to_email, subject, body)


def send_verification_email(smtp_settings, to_email: str, code: str) -> None:
    subject = "Verify your Digital Diary email address"
    body = (
        "Welcome to Digital Diary! Please verify your email address to "
        "finish setting up your account.\n\n"
        f"Your verification code is: {code}\n\n"
        "Enter this code on the verify email page. It's valid for 15 minutes "
        "and can only be used once.\n\n"
        "If you didn't create this account, you can safely ignore this email."
    )
    send_email(smtp_settings, to_email, subject, body)
