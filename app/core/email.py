"""Transactional email sending, using only the standard library.

Sends real multipart/alternative messages (HTML + plain-text fallback),
using a shared table-based HTML layout designed for email client
constraints (no flexbox/grid, inline styles, works in Outlook/Gmail/Apple
Mail, explicit light+dark color-scheme support).

If SMTP isn't configured (no smtp_host), the message is logged instead of
sent — convenient for local development, but be aware that in that mode
anyone who can read the server's logs can read a password-reset code.
Configure real SMTP before this ever handles real user accounts.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("app.email")

# Warm cream/ink/gold palette matching the app's own branding, chosen to
# still have solid contrast if an email client auto-inverts for dark mode.
_BRAND_INK = "#241a12"
_BRAND_ACCENT = "#c98a3e"
_BRAND_ACCENT_DARK = "#a06b2c"
_BG_BODY = "#f7f3ec"
_BG_CARD = "#ffffff"
_TEXT_PRIMARY = "#2a2018"
_TEXT_MUTED = "#6b6154"
_BORDER = "#e8ded0"


def _render_html_email(*, preheader: str, heading: str, intro_html: str, code: str | None, body_html: str, footer_note: str) -> str:
    """A single shared table-based layout for every transactional email.

    Table layout (not flexbox/grid) and inline styles throughout are
    deliberate -- this needs to render correctly in Outlook's Word-based
    engine and other email clients with poor modern-CSS support, not just
    real browsers.
    """
    code_block = ""
    if code:
        # Wide letter-spacing + a large monospace-ish size makes the code
        # easy to read and manually type, which is the whole point of an
        # OTP email -- most people are copying this by eye, not by paste.
        code_block = f"""
        <tr>
          <td align="center" style="padding: 8px 0 28px 0;">
            <table role="presentation" cellpadding="0" cellspacing="0" style="background-color:{_BG_BODY}; border:1px solid {_BORDER}; border-radius:10px;">
              <tr>
                <td style="padding: 18px 32px; font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 700; letter-spacing: 10px; color: {_BRAND_ACCENT_DARK}; text-align: center;">
                  {code}
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    return f"""<!doctype html>
<html lang="en" style="margin:0; padding:0;">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>{heading}</title>
  <!--[if mso]>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <![endif]-->
  <style>
    /* Only a handful of email clients honor <style>, so nothing critical
       lives here — it's a progressive enhancement over the inline styles
       below, mainly for responsive stacking on narrow screens. */
    @media only screen and (max-width: 600px) {{
      .dd-container {{ width: 100% !important; }}
      .dd-padded {{ padding-left: 20px !important; padding-right: 20px !important; }}
    }}
  </style>
</head>
<body style="margin:0; padding:0; background-color:{_BG_BODY}; -webkit-text-size-adjust:100%; text-size-adjust:100%;">
  <!-- Preheader: hidden preview text shown next to the subject line in the inbox list -->
  <div style="display:none; max-height:0; overflow:hidden; opacity:0; mso-hide:all;">
    {preheader}
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_BG_BODY};">
    <tr>
      <td align="center" style="padding: 32px 16px;">

        <table role="presentation" class="dd-container" width="600" cellpadding="0" cellspacing="0" style="width:600px; max-width:100%;">

          <!-- Wordmark -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <span style="font-family: Georgia, 'Times New Roman', serif; font-size: 22px; font-weight: 700; color:{_BRAND_INK};">
                &#128214; Digital Diary
              </span>
            </td>
          </tr>

          <!-- Card -->
          <tr>
            <td class="dd-padded" style="background-color:{_BG_CARD}; border:1px solid {_BORDER}; border-radius:14px; padding: 40px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding-bottom: 8px; font-family: Georgia, 'Times New Roman', serif; font-size: 22px; font-weight: 700; color:{_TEXT_PRIMARY};">
                    {heading}
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-bottom: 20px; font-family: Arial, Helvetica, sans-serif; font-size: 15px; line-height: 1.6; color:{_TEXT_MUTED};">
                    {intro_html}
                  </td>
                </tr>
                {code_block}
                <tr>
                  <td style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.6; color:{_TEXT_MUTED};">
                    {body_html}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td align="center" style="padding: 24px 20px 0 20px; font-family: Arial, Helvetica, sans-serif; font-size: 12px; line-height: 1.6; color:{_TEXT_MUTED};">
              {footer_note}
              <br>This is an automated message from Digital Diary. Please don't reply to this email.
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_email(smtp_settings, to_email: str, subject: str, body: str, html_body: str | None = None) -> None:
    """Send a transactional email. If html_body is given, sends a real
    multipart/alternative message (HTML + the plain-text body as a
    fallback for clients that can't render HTML); otherwise sends
    plain-text only.
    """
    if not smtp_settings.smtp_host:
        logger.warning(
            "SMTP not configured (SMTP_HOST unset) - logging email instead of sending.\n"
            "To: %s\nSubject: %s\n%s",
            to_email, subject, body,
        )
        return

    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
    else:
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
    html_body = _render_html_email(
        preheader=f"Your password reset code is {code} — valid for 15 minutes.",
        heading="Reset your password",
        intro_html="We received a request to reset your Digital Diary password. Enter this code on the reset password page:",
        code=code,
        body_html=(
            "This code is valid for <strong>15 minutes</strong> and can only be used once."
            "<br><br>"
            "If you didn't request this, you can safely ignore this email — your password won't be changed."
        ),
        footer_note="If you didn't request a password reset, no action is needed.",
    )
    send_email(smtp_settings, to_email, subject, body, html_body)


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
    html_body = _render_html_email(
        preheader=f"Your verification code is {code} — valid for 15 minutes.",
        heading="Verify your email",
        intro_html="Welcome to Digital Diary! Please verify your email address to finish setting up your account:",
        code=code,
        body_html=(
            "This code is valid for <strong>15 minutes</strong> and can only be used once."
            "<br><br>"
            "If you didn't create this account, you can safely ignore this email."
        ),
        footer_note="If you didn't create a Digital Diary account, no action is needed.",
    )
    send_email(smtp_settings, to_email, subject, body, html_body)
