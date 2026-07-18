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

    def __post_init__(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
