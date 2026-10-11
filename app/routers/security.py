"""Routes for the second step (PIN / passkey), PIN + passkey recovery and passkey management."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import repositories, security_factors as sf, services
from app.core.config import settings
from app.db.session import get_db
from app.deps import ensure_csrf_cookie, get_optional_user, verify_csrf
from app.routers.web import _base_context, _redirect, _response_with_csrf, _safe_msg, _set_auth_cookies, templates

router = APIRouter(tags=["security"], include_in_schema=False)
logger = logging.getLogger("app.security")

MFA_COOKIE = "mfa_token"
TRUSTED_COOKIE = "trusted_device"
CHALLENGE_COOKIE = "wa_challenge"


def _cookie(response, name: str, value: str, max_age: int, path: str = "/") -> None:
    response.set_cookie(name, value, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=max_age, path=path)


def _check_json_csrf(request: Request) -> None:
    verify_csrf(request, request.headers.get("x-csrf-token"))


def _json_error(exc: Exception, default: int = 400) -> JSONResponse:
    code = getattr(exc, "status_code", default)
    return JSONResponse({"ok": False, "detail": getattr(exc, "detail", None) or "Something went wrong"}, status_code=code)


def _valid_new_password(pw: str) -> str:
    if not pw or len(pw) < 8 or len(pw) > 128:
        raise HTTPException(status_code=400, detail="Password must be 8 to 128 characters")
    return pw


def finish_login(request: Request, user, *, remember: bool, as_json: bool):
    """Issue the real session after the second step; optionally remember this device."""
    access, refresh = services.issue_tokens(user)
    if as_json:
        response = JSONResponse({"ok": True, "redirect": "/dashboard"})
    else:
        response = _redirect("/dashboard")
    _set_auth_cookies(response, access, refresh)
    response.delete_cookie(MFA_COOKIE, path="/login")
    response.delete_cookie(CHALLENGE_COOKIE, path="/")
    if remember:
        _cookie(response, TRUSTED_COOKIE, sf.create_trusted_token(user), int(sf.TRUSTED_TTL.total_seconds()))
    response.set_cookie("csrf_token", ensure_csrf_cookie(request), httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_samesite)
    return response


def _pending_user(request: Request, db: Session):
    try:
        return sf.read_mfa_user(db, request.cookies.get(MFA_COOKIE))
    except ValueError:
        return None


# ------------------------------------------------------------------ login: second step
@router.get("/login/verify")
def login_verify_page(request: Request, db: Session = Depends(get_db)):
    user = _pending_user(request, db)
    if not user:
        return _redirect("/login?err=Please+sign+in+again")
    ctx = _base_context(request, None) | {"has_passkey": bool(sf.list_credentials(db, user)), "username": user.username}
    return _response_with_csrf(request, templates.TemplateResponse(request, "login_verify.html", ctx))


@router.post("/login/verify/pin")
def login_verify_pin(
    request: Request,
    pin: str = Form(...),
    csrf_token: str = Form(...),
    remember: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        verify_csrf(request, csrf_token)
        user = _pending_user(request, db)
        if not user:
            return _redirect("/login?err=Please+sign+in+again")
        if not sf.check_pin(db, user, pin):
            return _redirect("/login/verify?err=That+PIN+is+not+right")
    except Exception as exc:
        return _redirect(f"/login/verify?err={_safe_msg(exc)}")
    return finish_login(request, user, remember=bool(remember), as_json=False)


@router.post("/login/verify/webauthn/options")
async def login_verify_webauthn_options(request: Request, db: Session = Depends(get_db)):
    try:
        _check_json_csrf(request)
        user = _pending_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Please sign in again")
        options, token = sf.begin_authentication(db, user, request, "login")
    except Exception as exc:
        return _json_error(exc)
    response = JSONResponse({"ok": True, "options": options})
    _cookie(response, CHALLENGE_COOKIE, token, int(sf.CHALLENGE_TTL.total_seconds()))
    return response


@router.post("/login/verify/webauthn/finish")
async def login_verify_webauthn_finish(request: Request, db: Session = Depends(get_db)):
    try:
        _check_json_csrf(request)
        body = await request.json()
        user = _pending_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Please sign in again")
        if not sf.finish_authentication(db, user, request, body.get("credential") or {}, request.cookies.get(CHALLENGE_COOKIE), "login"):
            raise HTTPException(status_code=400, detail="That fingerprint or face wasn't recognised. Use your PIN instead.")
    except Exception as exc:
        return _json_error(exc)
    return finish_login(request, user, remember=bool(body.get("remember")), as_json=True)


# ------------------------------------------------------------------ settings: PIN and passkeys
def _need_user(current_user):
    return None if current_user else _redirect("/login")


@router.post("/settings/pin")
def settings_set_pin(
    request: Request,
    current_password: str = Form(""),
    pin: str = Form(...),
    confirm_pin: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        if pin != confirm_pin:
            return _redirect("/settings?err=The+PINs+do+not+match#security")
        sf.set_pin(db, current_user, pin, current_password)
    except Exception as exc:
        return _redirect(f"/settings?err={_safe_msg(exc)}#security")
    return _redirect("/settings?msg=Security+PIN+saved#security")


@router.post("/settings/pin/remove")
def settings_remove_pin(
    request: Request,
    current_password: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        sf.remove_pin(db, current_user, current_password)
    except Exception as exc:
        return _redirect(f"/settings?err={_safe_msg(exc)}#security")
    response = _redirect("/settings?msg=Security+PIN+and+passkeys+removed#security")
    response.delete_cookie(TRUSTED_COOKIE)
    return response


@router.post("/settings/passkeys/options")
async def settings_passkey_options(request: Request, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Please sign in")
        _check_json_csrf(request)
        options, token = sf.begin_registration(db, current_user, request)
    except Exception as exc:
        return _json_error(exc)
    response = JSONResponse({"ok": True, "options": options})
    _cookie(response, CHALLENGE_COOKIE, token, int(sf.CHALLENGE_TTL.total_seconds()))
    return response


@router.post("/settings/passkeys/finish")
async def settings_passkey_finish(request: Request, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="Please sign in")
        _check_json_csrf(request)
        body = await request.json()
        sf.finish_registration(db, current_user, request, body.get("credential") or {}, request.cookies.get(CHALLENGE_COOKIE), body.get("name") or "")
    except Exception as exc:
        return _json_error(exc)
    response = JSONResponse({"ok": True})
    response.delete_cookie(CHALLENGE_COOKIE, path="/")
    response.delete_cookie(TRUSTED_COOKIE)  # factors changed: devices must prove themselves again
    return response


@router.post("/settings/passkeys/{credential_id}/delete")
def settings_passkey_delete(
    credential_id: str,
    request: Request,
    current_password: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        sf.remove_credential(db, current_user, credential_id, current_password)
    except Exception as exc:
        return _redirect(f"/settings?err={_safe_msg(exc)}#security")
    return _redirect("/settings?msg=Passkey+removed#security")


# ------------------------------------------------------------------ recovery (no email needed)
@router.post("/forgot-password/pin-reset")
async def forgot_pin_reset(request: Request, db: Session = Depends(get_db)):
    try:
        _check_json_csrf(request)
        body = await request.json()
        _valid_new_password(body.get("new_password", ""))
        sf.reset_password_with_pin(db, body.get("username", ""), body.get("pin", ""), body["new_password"])
    except Exception as exc:
        return _json_error(exc)
    return JSONResponse({"ok": True, "detail": "Password changed. You can sign in now."})


@router.post("/forgot-password/webauthn/options")
async def forgot_webauthn_options(request: Request, db: Session = Depends(get_db)):
    try:
        _check_json_csrf(request)
        body = await request.json()
        user = repositories.get_user_by_username(db, (body.get("username") or "").strip())
        options, token = sf.begin_authentication(db, user, request, "recover")
    except Exception as exc:
        return _json_error(exc)
    response = JSONResponse({"ok": True, "options": options})
    _cookie(response, CHALLENGE_COOKIE, token, int(sf.CHALLENGE_TTL.total_seconds()))
    return response


@router.post("/forgot-password/webauthn/finish")
async def forgot_webauthn_finish(request: Request, db: Session = Depends(get_db)):
    try:
        _check_json_csrf(request)
        body = await request.json()
        user = repositories.get_user_by_username(db, (body.get("username") or "").strip())
        if not sf.finish_authentication(db, user, request, body.get("credential") or {}, request.cookies.get(CHALLENGE_COOKIE), "recover"):
            raise HTTPException(status_code=400, detail="That fingerprint or face wasn't recognised for this account")
        grant = sf.create_recovery_grant(user)
    except Exception as exc:
        return _json_error(exc)
    response = JSONResponse({"ok": True, "grant": grant})
    response.delete_cookie(CHALLENGE_COOKIE, path="/")
    return response


@router.post("/forgot-password/reset-with-grant")
async def forgot_reset_with_grant(request: Request, db: Session = Depends(get_db)):
    try:
        _check_json_csrf(request)
        body = await request.json()
        _valid_new_password(body.get("new_password", ""))
        sf.reset_password_with_grant(db, body.get("grant", ""), body["new_password"])
    except Exception as exc:
        return _json_error(exc)
    return JSONResponse({"ok": True, "detail": "Password changed. You can sign in now."})
