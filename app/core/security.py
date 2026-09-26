from __future__ import annotations

from datetime import UTC, datetime, timedelta
import secrets

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    payload = {
        "sub": subject,
        "typ": token_type,
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_access_token(subject: str) -> str:
    return _create_token(subject, "access", timedelta(minutes=settings.access_token_minutes))


def create_refresh_token(subject: str) -> str:
    return _create_token(subject, "refresh", timedelta(days=settings.refresh_token_days))


def decode_token(token: str, expected_type: str) -> str:
    # jwt.decode raises jwt.PyJWTError (ExpiredSignatureError,
    # DecodeError, InvalidSignatureError, ...) for an expired, malformed,
    # or tampered token. PyJWTError is a plain Exception subclass, not a
    # ValueError -- every caller of this function only catches ValueError
    # (that's the contract this function is supposed to uphold), so
    # without this translation, the single most common case of all --
    # a normal user's access token simply expiring after
    # access_token_minutes, or their refresh token after
    # refresh_token_days -- fell through as an unhandled exception. On
    # web routes that meant get_optional_user's caller crashed instead
    # of quietly treating the visitor as logged-out; on /api/auth/refresh
    # it meant a 500 instead of the 401 an API client actually needs to
    # know to send the user back through login.
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    if payload.get("typ") != expected_type:
        raise ValueError("Invalid token type")
    subject = payload.get("sub")
    if not subject:
        raise ValueError("Missing token subject")
    return str(subject)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
