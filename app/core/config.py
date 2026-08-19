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

    # Master switch for the whole email subsystem. Defaults on. Turn this
    # off (EMAIL_SERVICE_ENABLED=false) for a deployment that has no SMTP
    # story at all and doesn't want the OTP-gated flows around at all --
    # not degraded, not logged-to-console-as-a-fallback, just absent:
    # registration never generates or expects a verification code, no
    # "please verify your email" banner ever renders, /verify-email
    # redirects away, and "Forgot password?" / the whole reset-password
    # flow disappears from the UI and its routes refuse to run. This is
    # a different, stronger switch than "is SMTP configured" (smtp_host
    # above) -- that one silently falls back to console-logging codes,
    # which is a reasonable *development* default but still presents the
    # OTP UI/copy to the user. This one removes that UI entirely.
    email_service_enabled: bool = os.getenv("EMAIL_SERVICE_ENABLED", "true").lower() == "true"

    # Google OAuth ("Sign in with Google"). Both must be set for the
    # feature to activate; if either is blank the login/register pages
    # simply don't render the Google button and the /auth/google/*
    # routes return a clear error instead of silently misbehaving.
    # Get these from https://console.cloud.google.com/apis/credentials
    # (OAuth client ID, type "Web application"). Add
    # {APP_BASE_URL}/auth/google/callback as an authorized redirect URI there.
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    def __post_init__(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


settings = Settings()
