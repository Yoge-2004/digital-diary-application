"""Second step after the password (a PIN and/or a passkey), PIN/passkey account recovery, and
"remember this device".

Everything here is opt-in per account: an account with no PIN and no passkey signs in exactly as
before. The state lives in three places only:
  * users.pin_hash (+ lockout counters), webauthn_credentials  -- what the user registered
  * short-lived signed cookies/tokens (JWT, the app's own secret): the half-signed-in "mfa" token,
    the "trusted device" token, the passkey challenge, and the recovery grant
  * users.sec_version -- bumped on any change, which invalidates every token minted before it
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models import User, WebAuthnCredential

PIN_RE = re.compile(r"^\d{6,8}$")
PIN_MAX_FAILURES = 5
PIN_LOCK_MINUTES = 15
MFA_TTL = timedelta(minutes=5)
CHALLENGE_TTL = timedelta(minutes=5)
RECOVERY_TTL = timedelta(minutes=10)
TRUSTED_TTL = timedelta(days=30)
RESET_MAX_ATTEMPTS = 5

_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    """So 'no such user' costs the same bcrypt time as 'wrong PIN' (no account probing by timing)."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("000000")
    return _DUMMY_HASH


# --------------------------------------------------------------------------- tokens
def _sign(typ: str, sub: str, ttl: timedelta, **extra) -> str:
    payload = {"typ": typ, "sub": sub, "exp": datetime.now(UTC) + ttl, **extra}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _read(token: str | None, typ: str) -> dict:
    if not token:
        raise ValueError("missing token")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ValueError("invalid or expired token") from exc
    if payload.get("typ") != typ or not payload.get("sub"):
        raise ValueError("wrong token type")
    return payload


def sec_version(user: User) -> int:
    return user.sec_version or 0


def bump_version(db: Session, user: User) -> None:
    user.sec_version = sec_version(user) + 1
    db.commit()


# --------------------------------------------------------------------------- state
def has_pin(user: User) -> bool:
    return bool(user.pin_hash)


def list_credentials(db: Session, user: User) -> list[WebAuthnCredential]:
    return (
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.user_id == user.id)
        .order_by(WebAuthnCredential.created_at)
        .all()
    )


def has_second_factor(db: Session, user: User) -> bool:
    """The second step exists iff a PIN is set. Passkeys are a convenience on top of it, never
    instead of it: signing in from a device that has no passkey for the account must still be
    possible, and the PIN is that universal fallback."""
    return has_pin(user)


# --------------------------------------------------------------------------- PIN
def validate_pin_format(pin: str) -> str:
    pin = (pin or "").strip()
    if not PIN_RE.match(pin):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PIN must be 6 to 8 digits")
    return pin


def _require_password(user: User, password: str) -> None:
    # OAuth-only accounts have no password they know (a random one is stored), so they are
    # allowed to manage factors while signed in; everyone else must prove the current password.
    if user.oauth_provider:
        return
    if not password or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")


def set_pin(db: Session, user: User, pin: str, current_password: str) -> None:
    pin = validate_pin_format(pin)
    _require_password(user, current_password)
    user.pin_hash = hash_password(pin)
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    bump_version(db, user)


def remove_pin(db: Session, user: User, current_password: str) -> None:
    _require_password(user, current_password)
    user.pin_hash = None
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    # Without a PIN there is no second step, so passkeys would be orphaned; remove them too.
    for row in list_credentials(db, user):
        db.delete(row)
    bump_version(db, user)


def _locked_minutes(user: User) -> int:
    until = user.pin_locked_until
    if not until:
        return 0
    now = datetime.now(UTC)
    if not until.tzinfo:
        until = until.replace(tzinfo=UTC)
    remaining = (until - now).total_seconds()
    return max(0, int(remaining // 60) + 1) if remaining > 0 else 0


def check_pin(db: Session, user: User | None, pin: str) -> bool:
    """True if the PIN is right. Wrong PINs count towards a 15-minute lockout after 5 in a row;
    while locked even the right PIN is refused, so the lockout can't be probed."""
    if user is None or not user.pin_hash:
        verify_password(pin or "", _dummy_hash())  # equalise timing
        return False
    minutes = _locked_minutes(user)
    if minutes:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many wrong PINs. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        )
    ok = bool(PIN_RE.match((pin or "").strip())) and verify_password(pin.strip(), user.pin_hash)
    if ok:
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
    else:
        user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
        if user.pin_failed_attempts >= PIN_MAX_FAILURES:
            user.pin_failed_attempts = 0
            user.pin_locked_until = datetime.now(UTC) + timedelta(minutes=PIN_LOCK_MINUTES)
    db.commit()
    return ok


# --------------------------------------------------------------------------- second step at login
def create_mfa_token(user: User) -> str:
    return _sign("mfa", user.id, MFA_TTL, v=sec_version(user))


def read_mfa_user(db: Session, token: str | None) -> User:
    payload = _read(token, "mfa")
    user = db.get(User, payload["sub"])
    if not user or payload.get("v") != sec_version(user):
        raise ValueError("stale")
    return user


def create_trusted_token(user: User) -> str:
    return _sign("trusted", user.id, TRUSTED_TTL, v=sec_version(user))


def is_trusted_device(user: User, token: str | None) -> bool:
    """'Caching' of the second step: a device that passed it and was remembered skips it for 30
    days, until the PIN / a passkey / the password changes (sec_version)."""
    try:
        payload = _read(token, "trusted")
    except ValueError:
        return False
    return payload["sub"] == user.id and payload.get("v") == sec_version(user)


# --------------------------------------------------------------------------- recovery
def create_recovery_grant(user: User) -> str:
    return _sign("recover", user.id, RECOVERY_TTL, v=sec_version(user))


def reset_password_with_pin(db: Session, username: str, pin: str, new_password: str) -> User:
    from app import repositories

    user = repositories.get_user_by_username(db, (username or "").strip())
    if not check_pin(db, user, pin):
        # one message for: no such user, no PIN set, wrong PIN
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That username and PIN don't match")
    repositories.update_user_password(db, user, hash_password(new_password))
    bump_version(db, user)
    return user


def reset_password_with_grant(db: Session, grant: str, new_password: str) -> User:
    from app import repositories

    try:
        payload = _read(grant, "recover")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This recovery link has expired. Start again.")
    user = db.get(User, payload["sub"])
    if not user or payload.get("v") != sec_version(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This recovery link has expired. Start again.")
    repositories.update_user_password(db, user, hash_password(new_password))
    bump_version(db, user)
    return user


def note_wrong_reset_code(db: Session, user: User) -> None:
    """The emailed 6-digit code had no attempt limit (a million guesses inside its 15 minutes).
    Five wrong tries now burn it."""
    user.reset_attempts = (user.reset_attempts or 0) + 1
    if user.reset_attempts >= RESET_MAX_ATTEMPTS:
        user.reset_token = None
        user.reset_token_expires = None
        user.reset_attempts = 0
    db.commit()


# --------------------------------------------------------------------------- passkeys (WebAuthn)
def webauthn_rp(request: Request) -> tuple[str, str]:
    """(rp_id, origin) this request should be verified against."""
    rp_id = settings.webauthn_rp_id or request.url.hostname or ""
    origin = settings.webauthn_origin
    if not origin:
        sent = request.headers.get("origin")
        origin = sent if sent and urlparse(sent).hostname == rp_id else f"{request.url.scheme}://{request.url.netloc}"
    if urlparse(origin).hostname != rp_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkeys are not available on this address")
    return rp_id, origin


def _challenge_token(purpose: str, user_id: str, challenge: bytes) -> str:
    from webauthn.helpers import bytes_to_base64url

    return _sign("wa", user_id, CHALLENGE_TTL, purpose=purpose, ch=bytes_to_base64url(challenge))


def _read_challenge(token: str | None, purpose: str, user_id: str) -> bytes:
    from webauthn.helpers import base64url_to_bytes

    try:
        payload = _read(token, "wa")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That request expired. Please try again.")
    if payload.get("purpose") != purpose or payload["sub"] != user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That request expired. Please try again.")
    return base64url_to_bytes(payload["ch"])


def begin_registration(db: Session, user: User, request: Request) -> tuple[dict, str]:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorAttachment,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )
    from webauthn.helpers import base64url_to_bytes

    if not has_pin(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Set a security PIN first; it is the fallback for devices without a fingerprint or face sensor")
    rp_id, _ = webauthn_rp(request)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user.id.encode(),
        user_name=user.username,
        user_display_name=user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.DISCOURAGED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in list_credentials(db, user)
        ],
    )
    return json.loads(options_to_json(options)), _challenge_token("register", user.id, options.challenge)


def finish_registration(db: Session, user: User, request: Request, credential: dict, challenge_token: str | None, name: str) -> WebAuthnCredential:
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url

    rp_id, origin = webauthn_rp(request)
    challenge = _read_challenge(challenge_token, "register", user.id)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="We couldn't verify that fingerprint or face. Please try again.")
    cred_id = bytes_to_base64url(verified.credential_id)
    if db.query(WebAuthnCredential).filter(WebAuthnCredential.credential_id == cred_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That device is already registered")
    row = WebAuthnCredential(
        user_id=user.id,
        credential_id=cred_id,
        public_key=bytes_to_base64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        name=(name or "This device").strip()[:80] or "This device",
    )
    db.add(row)
    db.commit()
    bump_version(db, user)
    return row


def remove_credential(db: Session, user: User, credential_row_id: str, current_password: str) -> None:
    _require_password(user, current_password)
    row = db.query(WebAuthnCredential).filter(WebAuthnCredential.id == credential_row_id, WebAuthnCredential.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")
    db.delete(row)
    db.commit()
    bump_version(db, user)


def begin_authentication(db: Session, user: User | None, request: Request, purpose: str) -> tuple[dict, str]:
    """Options for signing in / recovering with a passkey. For an unknown user (or one with no
    passkey) a random credential id is offered, so the response doesn't reveal which usernames
    have passkeys; the browser prompt simply fails."""
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

    rp_id, _ = webauthn_rp(request)
    creds = list_credentials(db, user) if user else []
    allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in creds] or [
        PublicKeyCredentialDescriptor(id=secrets.token_bytes(32))
    ]
    options = generate_authentication_options(rp_id=rp_id, allow_credentials=allow, user_verification=UserVerificationRequirement.REQUIRED)
    return json.loads(options_to_json(options)), _challenge_token(purpose, user.id if user else "-", options.challenge)


def finish_authentication(db: Session, user: User | None, request: Request, credential: dict, challenge_token: str | None, purpose: str) -> bool:
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes

    if user is None:
        return False
    rp_id, origin = webauthn_rp(request)
    challenge = _read_challenge(challenge_token, purpose, user.id)
    raw_id = credential.get("id") if isinstance(credential, dict) else None
    row = next((c for c in list_credentials(db, user) if c.credential_id == raw_id), None)
    if row is None:
        return False
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=base64url_to_bytes(row.public_key),
            credential_current_sign_count=row.sign_count,
            require_user_verification=True,
        )
    except Exception:
        return False
    row.sign_count = verified.new_sign_count
    row.last_used_at = datetime.now(UTC)
    db.commit()
    return True
