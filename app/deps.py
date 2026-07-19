from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import decode_token, generate_csrf_token
from app.db.session import get_db
from app import repositories


def _get_token_from_request(request: Request, access_token: str | None) -> str | None:
    if access_token:
        return access_token
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias="access_token"),
):
    token = _get_token_from_request(request, access_token)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        user_id = decode_token(token, "access")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    user = repositories.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias="access_token"),
):
    token = _get_token_from_request(request, access_token)
    if not token:
        return None
    try:
        user_id = decode_token(token, "access")
    except ValueError:
        return None
    return repositories.get_user_by_id(db, user_id)


def ensure_csrf_cookie(request: Request) -> str:
    token = request.cookies.get("csrf_token")
    if token:
        return token
    # No cookie yet (a visitor's very first request). Cache the freshly
    # generated token on request.state so every call during this same
    # request — one for the template context, one for the outgoing
    # Set-Cookie header — agrees on the same value. Without this, each
    # call minted its own random token, so the value rendered into the
    # page never matched the cookie the browser actually received,
    # and the very first form submission of a new visitor's session
    # (e.g. their registration) would always fail CSRF validation.
    cached = getattr(request.state, "csrf_token", None)
    if cached:
        return cached
    token = generate_csrf_token()
    request.state.csrf_token = token
    return token


def verify_csrf(request: Request, submitted_token: str | None) -> None:
    expected = request.cookies.get("csrf_token")
    if not expected or not submitted_token or submitted_token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
