from __future__ import annotations

import email as email_lib
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from app.core.email import send_email, send_password_reset_email, send_verification_email


@dataclass
class FakeSmtpSettings:
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_from: str = "noreply@example.com"
    smtp_user: str = "user"
    smtp_password: str = "pass"
    smtp_use_tls: bool = True


def _sent_parts(mock_smtp_cls, send_fn, *args):
    """Call send_fn(settings, *args) with SMTP mocked out, and return the
    decoded (plain_text, html) parts that were actually handed to
    smtplib.SMTP.sendmail()."""
    server = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = server
    send_fn(FakeSmtpSettings(), *args)

    _from, _to, msg_string = server.sendmail.call_args[0]
    parsed = email_lib.message_from_string(msg_string)

    plain, html = None, None
    for part in parsed.walk():
        if part.get_content_type() == "text/plain":
            plain = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
        elif part.get_content_type() == "text/html":
            html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
    return plain, html, parsed


@patch("smtplib.SMTP")
def test_password_reset_email_is_multipart_with_html_and_plaintext(mock_smtp):
    plain, html, parsed = _sent_parts(mock_smtp, send_password_reset_email, "user@example.com", "482913")

    assert parsed.get_content_type() == "multipart/alternative"
    assert plain is not None and html is not None
    assert "482913" in plain
    assert "482913" in html


@patch("smtplib.SMTP")
def test_verification_email_is_multipart_with_html_and_plaintext(mock_smtp):
    plain, html, parsed = _sent_parts(mock_smtp, send_verification_email, "user@example.com", "999888")

    assert parsed.get_content_type() == "multipart/alternative"
    assert plain is not None and html is not None
    assert "999888" in plain
    assert "999888" in html


@patch("smtplib.SMTP")
def test_html_email_is_well_formed_and_responsive(mock_smtp):
    _plain, html, _parsed = _sent_parts(mock_smtp, send_password_reset_email, "user@example.com", "111222")

    assert html.strip().startswith("<!doctype html>")
    assert "<html" in html and "</html>" in html
    # Email-safe layout: table-based, not flexbox/grid, which many email
    # clients (notably Outlook) don't support.
    assert "<table" in html
    assert "display:flex" not in html and "display: flex" not in html
    assert "display:grid" not in html and "display: grid" not in html
    # Explicit light+dark support so clients that auto-invert colors
    # don't mangle it.
    assert 'name="color-scheme"' in html
    assert 'name="supported-color-schemes"' in html
    # A responsive media query for narrow (mobile) viewports.
    assert "@media" in html and "max-width: 600px" in html
    # Hidden preheader text (the inbox preview snippet).
    assert "111222" in html


@patch("smtplib.SMTP")
def test_html_email_does_not_leak_raw_code_only_as_plain_digits_without_formatting(mock_smtp):
    """Sanity check that the OTP code is actually rendered inside the
    styled code block, not just incidentally present somewhere in the
    markup (e.g. only in the hidden preheader)."""
    _plain, html, _parsed = _sent_parts(mock_smtp, send_verification_email, "user@example.com", "555444")
    assert "letter-spacing" in html  # the code block's styling
    # the code block appears after the intro text, inside the card
    card_start = html.index("Verify your email")
    assert html.index("555444", card_start) > card_start


def test_send_email_without_html_body_still_sends_plaintext_only():
    """send_email() must stay usable for plain-text-only callers (its
    original signature), not force multipart everywhere."""
    with patch("smtplib.SMTP") as mock_smtp:
        server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = server
        send_email(FakeSmtpSettings(), "user@example.com", "Plain subject", "Plain body text")

        _from, _to, msg_string = server.sendmail.call_args[0]
        parsed = email_lib.message_from_string(msg_string)
        assert parsed.get_content_type() == "text/plain"


def test_no_smtp_configured_logs_plaintext_not_raw_html(caplog):
    """The local-dev fallback (no SMTP_HOST) should log the readable
    plain-text version, not dump raw HTML markup into the server log."""
    import logging
    caplog.set_level(logging.WARNING, logger="app.email")

    @dataclass
    class NoSmtp:
        smtp_host: str = ""
        smtp_port: int = 587
        smtp_from: str = "noreply@example.com"
        smtp_user: str = ""
        smtp_password: str = ""
        smtp_use_tls: bool = True

    send_verification_email(NoSmtp(), "user@example.com", "777666")
    logged = caplog.text
    assert "777666" in logged
    assert "<html" not in logged
    assert "<table" not in logged
