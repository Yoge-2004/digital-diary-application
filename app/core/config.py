from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Digital Diary")
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production-please-use-a-longer-secret")
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'digital_diary.db'}")
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "1440"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    cookie_samesite: str = os.getenv("COOKIE_SAMESITE", "lax")
    upload_dir: Path = field(default_factory=lambda: BASE_DIR / "uploads")

    # Password-reset emails. If smtp_host is empty, reset links are logged
    # to the server console instead of emailed — safe for local dev, but
    # NOT a substitute for real SMTP in any deployment with real users:
    # without real delivery, whoever can read the server logs can also
    # reset any account's password.
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "no-reply@example.com")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    app_base_url: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")

    # Passkeys (WebAuthn). Leave empty to derive the relying-party id / origin from each request;
    # set them when running behind a proxy that rewrites the host or scheme (the browser checks
    # that the origin it saw is the one the server expects).
    webauthn_rp_id: str = os.getenv("WEBAUTHN_RP_ID", "")
    webauthn_origin: str = os.getenv("WEBAUTHN_ORIGIN", "")
    webauthn_rp_name: str = os.getenv("WEBAUTHN_RP_NAME", "Digital Diary")

    # Master switch for the whole email subsystem. Turn this off
    # (EMAIL_SERVICE_ENABLED=false) -- or just leave SMTP unconfigured --
    # for a deployment that doesn't want the OTP-gated flows around at
    # all: not degraded, not logged-to-console-as-a-fallback, just
    # absent. Registration never generates or expects a verification
    # code, no "please verify your email" banner ever renders,
    # /verify-email redirects away, and "Forgot password?" / the whole
    # reset-password flow disappears from the UI and its routes refuse
    # to run.
    #
    # Default is derived from smtp_host, NOT hardcoded true: with no SMTP
    # configured, there's no real way to deliver a verification/reset
    # email, so presenting that UI out of the box is misleading -- it
    # promises an email that never arrives. Set EMAIL_SERVICE_ENABLED
    # explicitly (true/false) to override this in either direction, e.g.
    # to keep the OTP flow running with codes logged to the server
    # console for local development despite no SMTP, or to force it off
    # even with SMTP configured.
    #
    # This is resolved in __post_init__ (not as a plain field default)
    # deliberately: a plain `= os.getenv(...)` default expression is
    # evaluated exactly once, at class-definition/import time, and then
    # reused for every Settings() call afterwards -- so it can never see
    # self.smtp_host (which may itself have been passed explicitly to a
    # given instance) and can't be exercised by tests that set env vars
    # at runtime. Resolving it per-instance, from the actual smtp_host
    # this instance ended up with, is both correct in production and
    # testable.
    email_service_enabled: bool | None = None

    # Google OAuth ("Sign in with Google"). Both must be set for the
    # feature to activate; if either is blank the login/register pages
    # simply don't render the Google button and the /auth/google/*
    # routes return a clear error instead of silently misbehaving.
    # Get these from https://console.cloud.google.com/apis/credentials
    # (OAuth client ID, type "Web application"). Add
    # {APP_BASE_URL}/auth/google/callback as an authorized redirect URI there.
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # Web Push (daily "write today" reminders). Needs a VAPID key pair --
    # generate one with:
    #   python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); \
    #     print(v.public_key.public_bytes(...))"
    # or more simply `vapid --gen` from the py-vapid package (installed as
    # a pywebpush dependency). Both keys must be set for the feature to
    # activate; if either is blank, the Settings > Notifications UI
    # doesn't render the toggle at all rather than showing a broken
    # control that can never actually deliver anything, and the
    # subscribe/unsubscribe API routes return a clear error instead of
    # silently failing. Same reasoning as google_oauth_enabled above.
    vapid_public_key: str = os.getenv("VAPID_PUBLIC_KEY", "")
    vapid_private_key: str = os.getenv("VAPID_PRIVATE_KEY", "")
    # VAPID requires a contact URI (mailto: or https:) in the JWT claims
    # so a push service operator has a way to reach whoever's sending
    # through them if something goes wrong.
    vapid_claims_sub: str = os.getenv("VAPID_CLAIMS_SUB", "mailto:no-reply@example.com")

    def __post_init__(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        if self.email_service_enabled is None:
            env_val = os.getenv("EMAIL_SERVICE_ENABLED")
            resolved = (
                env_val.lower() == "true"
                if env_val is not None
                else bool(self.smtp_host)
            )
            object.__setattr__(self, "email_service_enabled", resolved)

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def push_notifications_enabled(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key)


settings = Settings()
