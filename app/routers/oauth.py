"""Google OAuth ("Sign in with Google").

Two routes:
  GET /auth/google/login    -- redirects the browser to Google's consent screen
  GET /auth/google/callback -- Google redirects back here with a `code`

This deliberately does its own minimal Authorization Code flow with
`httpx` rather than pulling in a dependency like authlib, since the app
only needs one provider and the flow is short. If more providers are
added later, this is the place to generalize.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db.session import get_db
from app import services
from app.routers.web import _redirect, _set_auth_cookies  # reuse the exact same session-creation helpers as password login

router = APIRouter(tags=["oauth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

STATE_COOKIE = "oauth_state"


def _callback_url(request: Request) -> str:
    """Build the redirect_uri Google should send the browser back to.

    Must exactly match (scheme, host, path) one of the "Authorized redirect
    URIs" configured for this OAuth client in Google Cloud Console.
    """
    return str(request.url_for("google_callback"))


@router.get("/auth/google/login")
def google_login(request: Request):
    settings = request.app.state.settings
    if not settings.google_oauth_enabled:
        return _redirect("/login?err=Google+sign-in+is+not+configured+on+this+server")

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _callback_url(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    # Short-lived, httponly cookie to verify the `state` we get back on the
    # callback actually originated from this browser (CSRF protection for
    # the OAuth flow) -- not the app's own csrf_token, since this needs to
    # survive a full redirect to Google and back.
    response.set_cookie(
        STATE_COOKIE, state, httponly=True, max_age=600,
        secure=settings.cookie_secure, samesite="lax",
    )
    return response


@router.get("/auth/google/callback", name="google_callback")
def google_callback(request: Request, db: Session = Depends(get_db)):
    settings = request.app.state.settings
    if not settings.google_oauth_enabled:
        return _redirect("/login?err=Google+sign-in+is+not+configured+on+this+server")

    error = request.query_params.get("error")
    if error:
        return _redirect(f"/login?err=Google+sign-in+was+cancelled")

    code = request.query_params.get("code")
    returned_state = request.query_params.get("state")
    expected_state = request.cookies.get(STATE_COOKIE)

    if not code or not returned_state or not expected_state or returned_state != expected_state:
        return _redirect("/login?err=Google+sign-in+failed+%28invalid+state%29")

    try:
        with httpx.Client(timeout=10.0) as client:
            token_resp = client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": _callback_url(request),
                "grant_type": "authorization_code",
            })
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            userinfo_resp = client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
            userinfo_resp.raise_for_status()
            info = userinfo_resp.json()
    except (httpx.HTTPError, KeyError):
        return _redirect("/login?err=Couldn%27t+reach+Google+-+please+try+again")

    google_id = info.get("sub")
    email = info.get("email")
    name = info.get("name")
    if not google_id or not email:
        return _redirect("/login?err=Google+didn%27t+share+an+email+for+this+account")
    if info.get("email_verified") is False:
        return _redirect("/login?err=Please+verify+your+email+with+Google+first")

    user = services.get_or_create_oauth_user(db, provider="google", provider_user_id=google_id, email=email, name=name)
    access_token_jwt, refresh_token_jwt = services.issue_tokens(user)

    response = _redirect("/dashboard")
    _set_auth_cookies(response, access_token_jwt, refresh_token_jwt)
    response.delete_cookie(STATE_COOKIE)
    return response
