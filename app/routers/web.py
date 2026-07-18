from __future__ import annotations

import calendar as cal_module
import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR, settings
from app.deps import ensure_csrf_cookie, get_optional_user, verify_csrf
from app.db.session import get_db
from app import repositories, services
from app.schemas import DiaryCreate, DiaryUpdate, PasswordUpdate, UserCreate, UserUpdate


router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def _response_with_csrf(request: Request, response: RedirectResponse | HTMLResponse):
    csrf_token = ensure_csrf_cookie(request)
    if request.cookies.get("csrf_token") != csrf_token:
        response.set_cookie(
            "csrf_token",
            csrf_token,
            httponly=False,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )
    return response


def _base_context(request: Request, user):
    return {
        "request": request,
        "current_user": user,
        "csrf_token": request.cookies.get("csrf_token") or ensure_csrf_cookie(request),
        "flash": request.query_params.get("msg"),
        "flash_error": request.query_params.get("err"),
    }


def _redirect(location: str) -> RedirectResponse:
    return RedirectResponse(location, status_code=303)


def _redirect_with_msg(location: str, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    if err:
        sep = "&" if "?" in location else "?"
        location = f"{location}{sep}err={err}"
    elif msg:
        sep = "&" if "?" in location else "?"
        location = f"{location}{sep}msg={msg}"
    return RedirectResponse(location, status_code=303)


# ──────────────────────────────────────────
# Auth
# ──────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    if current_user:
        return _redirect("/dashboard")
    context = _base_context(request, None)
    return _response_with_csrf(request, templates.TemplateResponse(request, "landing.html", context))


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, current_user=Depends(get_optional_user)):
    if current_user:
        return _redirect("/dashboard")
    return _response_with_csrf(
        request,
        templates.TemplateResponse(request, "auth.html", _base_context(request, None) | {"auth_mode": "register"}),
    )


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        verify_csrf(request, csrf_token)
        user = services.register_user(db, UserCreate(username=username, email=email, password=password))
    except Exception as exc:
        return _redirect(f"/register?err={_safe_msg(exc)}")
    access_token, refresh_token = services.issue_tokens(user)
    response = _redirect("/dashboard")
    _set_auth_cookies(response, access_token, refresh_token)
    response.set_cookie("csrf_token", ensure_csrf_cookie(request), httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_samesite)
    return response


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, current_user=Depends(get_optional_user)):
    if current_user:
        return _redirect("/dashboard")
    return _response_with_csrf(
        request,
        templates.TemplateResponse(request, "auth.html", _base_context(request, None) | {"auth_mode": "login"}),
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        verify_csrf(request, csrf_token)
        user = services.authenticate_user(db, username, password)
    except Exception as exc:
        return _redirect(f"/login?err={_safe_msg(exc)}")
    access_token, refresh_token = services.issue_tokens(user)
    response = _redirect("/dashboard")
    _set_auth_cookies(response, access_token, refresh_token)
    response.set_cookie("csrf_token", ensure_csrf_cookie(request), httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_samesite)
    return response


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    try:
        verify_csrf(request, csrf_token)
    except Exception:
        pass
    response = _redirect("/")
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request, current_user=Depends(get_optional_user)):
    if current_user:
        return _redirect("/dashboard")
    return _response_with_csrf(
        request,
        templates.TemplateResponse(
            request,
            "forgot_password.html",
            _base_context(request, None),
        ),
    )


@router.post("/forgot-password/verify")
async def forgot_password_verify(request: Request, db: Session = Depends(get_db)):
    """Step 1 — verify username + email pair exists."""
    from fastapi.responses import JSONResponse
    try:
        body = await request.json()
        username = body.get("username", "").strip()
        email    = body.get("email", "").strip()
        user = services.verify_reset_credentials(db, username, email)
        if user:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "detail": "No account found matching that username and email"}, status_code=404)
    except Exception as exc:
        return JSONResponse({"ok": False, "detail": str(exc)}, status_code=400)


@router.post("/forgot-password/reset")
async def forgot_password_reset(request: Request, db: Session = Depends(get_db)):
    """Step 2 — reset password after credentials verified."""
    from fastapi.responses import JSONResponse
    try:
        body = await request.json()
        username     = body.get("username", "").strip()
        email        = body.get("email", "").strip()
        new_password = body.get("new_password", "")
        if len(new_password) < 8:
            return JSONResponse({"ok": False, "detail": "Password must be at least 8 characters"}, status_code=400)
        ok = services.reset_password_by_credentials(db, username, email, new_password)
        if ok:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "detail": "Unable to reset password — please try again"}, status_code=400)
    except Exception as exc:
        return JSONResponse({"ok": False, "detail": str(exc)}, status_code=400)


# ──────────────────────────────────────────
# Dashboard / Stats / Calendar
# ──────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    if not current_user:
        return _redirect("/login")
    summary = services.diary_summary(db, current_user)
    return _response_with_csrf(
        request,
        templates.TemplateResponse(request, "dashboard.html", _base_context(request, current_user) | {
            "summary": summary,
            "now": datetime.now(),
        }),
    )


@router.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    if not current_user:
        return _redirect("/login")
    summary = services.diary_summary(db, current_user)
    return _response_with_csrf(
        request,
        templates.TemplateResponse(request, "stats.html", _base_context(request, current_user) | {"summary": summary}),
    )


@router.get("/calendar", response_class=HTMLResponse)
def calendar_page(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    now = datetime.now(UTC)
    year = year or now.year
    month = month or now.month
    # clamp month
    month = max(1, min(12, month))

    diaries = repositories.list_diaries_for_calendar(db, current_user.id, year, month)

    # build day -> count map
    day_counts: dict[int, int] = {}
    for d in diaries:
        day = d.created_at.day
        day_counts[day] = day_counts.get(day, 0) + 1

    # calendar matrix
    cal = cal_module.monthcalendar(year, month)
    month_name = cal_module.month_name[month]

    # prev / next navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return _response_with_csrf(
        request,
        templates.TemplateResponse(
            request,
            "calendar.html",
            _base_context(request, current_user) | {
                "year": year,
                "month": month,
                "month_name": month_name,
                "cal": cal,
                "day_counts": day_counts,
                "prev_year": prev_year,
                "prev_month": prev_month,
                "next_year": next_year,
                "next_month": next_month,
                "now": datetime.now(),
            },
        ),
    )


# ──────────────────────────────────────────
# Diaries
# ──────────────────────────────────────────

@router.get("/diaries", response_class=HTMLResponse)
def diaries(
    request: Request,
    search: str | None = None,
    tag: str | None = None,
    mood: str | None = None,
    favorite: bool | None = None,
    bookmarked: bool | None = None,
    archived: bool | None = None,
    month: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    # If archived filter not set, default hides archived (repositories default)
    entries = services.list_diaries(
        db,
        current_user,
        search=search,
        tag=tag,
        mood=mood,
        favorite=favorite,
        bookmarked=bookmarked,
        archived=archived,
        month=month,
        year=year,
    )
    all_tags = repositories.list_tags(db, current_user.id)
    # Filter pinned diaries from normal ones
    pinned_diaries = [d for d in entries if d.is_pinned]
    non_pinned_diaries = [d for d in entries if not d.is_pinned]
    
    return _response_with_csrf(
        request,
        templates.TemplateResponse(
            request,
            "diaries.html",
            _base_context(request, current_user) | {
                "diaries": non_pinned_diaries,
                "pinned_diaries": pinned_diaries,
                "all_tags": all_tags,
                "favorite": favorite,
                "bookmarked": bookmarked,
                "archived": archived,
                "mood_filter": mood,
                "tag_filter": tag,
                "q": search,
                "filters": {
                    "search": search,
                    "tag": tag,
                    "mood": mood,
                    "favorite": favorite,
                    "bookmarked": bookmarked,
                    "archived": archived,
                    "month": month,
                    "year": year,
                },
            },
        ),
    )




# IMPORTANT: /diaries/new must come BEFORE /diaries/{diary_id}
@router.get("/diaries/new", response_class=HTMLResponse)
def new_diary_page(request: Request, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    if not current_user:
        return _redirect("/login")
    all_tags = repositories.list_tags(db, current_user.id)
    return _response_with_csrf(
        request,
        templates.TemplateResponse(
            request,
            "diary_form.html",
            _base_context(request, current_user) | {"mode": "create", "diary": None, "all_tags": all_tags},
        ),
    )


@router.post("/diaries/new")
def new_diary(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    mood: str = Form("neutral"),
    visibility: str = Form("private"),
    location: str | None = Form(None),
    tags: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        diary = services.create_diary(
            db,
            current_user,
            DiaryCreate(title=title, content=content, mood=mood, visibility=visibility, location=location, tags=services.split_tags(tags)),
        )
    except Exception as exc:
        return _redirect(f"/diaries/new?err={_safe_msg(exc)}")
    return _redirect(f"/diaries/{diary.id}?msg=Entry+created")


@router.get("/diaries/{diary_id}", response_class=HTMLResponse)
def diary_detail(request: Request, diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    try:
        diary = services.get_diary(db, current_user, diary_id)
    except Exception:
        return _redirect("/diaries?err=Entry+not+found+or+access+denied")
        
    is_read_only = True
    shares = []
    if current_user and diary.user_id == current_user.id:
        is_read_only = False
        from app.models import DiaryShare
        from sqlalchemy import select
        shares = db.scalars(select(DiaryShare).where(DiaryShare.diary_id == diary.id)).all()
        
    return _response_with_csrf(
        request,
        templates.TemplateResponse(
            request, 
            "diary_detail.html", 
            _base_context(request, current_user) | {
                "diary": diary,
                "is_read_only": is_read_only,
                "shares": shares,
            }
        ),
    )


@router.get("/diaries/{diary_id}/edit", response_class=HTMLResponse)
def edit_diary_page(request: Request, diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    if not current_user:
        return _redirect("/login")
    diary = services.get_diary(db, current_user, diary_id)
    all_tags = repositories.list_tags(db, current_user.id)
    return _response_with_csrf(
        request,
        templates.TemplateResponse(
            request,
            "diary_form.html",
            _base_context(request, current_user) | {"mode": "edit", "diary": diary, "all_tags": all_tags},
        ),
    )


@router.post("/diaries/{diary_id}/edit")
def edit_diary(
    request: Request,
    diary_id: str,
    title: str = Form(...),
    content: str = Form(...),
    mood: str = Form("neutral"),
    visibility: str = Form("private"),
    location: str | None = Form(None),
    tags: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        diary = services.get_diary(db, current_user, diary_id)
        services.edit_diary(
            db,
            diary,
            DiaryUpdate(title=title, content=content, mood=mood, visibility=visibility, location=location, tags=services.split_tags(tags)),
        )
    except Exception as exc:
        return _redirect(f"/diaries/{diary_id}/edit?err={_safe_msg(exc)}")
    return _redirect(f"/diaries/{diary_id}?msg=Entry+updated")


def _toggle_and_redirect(request: Request, diary_id: str, flag: str, db: Session, current_user, back: str | None = None):
    """Toggle a boolean flag; return JSON if called via fetch, else redirect."""
    from fastapi.responses import JSONResponse
    if not current_user:
        if request.headers.get("X-Requested-With") == "fetch":
            return JSONResponse({"ok": False, "detail": "Not authenticated"}, status_code=401)
        return _redirect("/login")
    diary = services.get_diary(db, current_user, diary_id)
    services.toggle_flag(db, diary, flag)
    new_value = getattr(diary, flag)
    if request.headers.get("X-Requested-With") == "fetch":
        return JSONResponse({"ok": True, "flag": flag, "value": new_value})
    dest = back or f"/diaries/{diary_id}"
    return _redirect(dest)


@router.post("/diaries/{diary_id}/favorite")
async def favorite_diary(
    request: Request,
    diary_id: str,
    csrf_token: str = Form(default=""),
    back: str = Form("/diaries"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if request.headers.get("X-Requested-With") != "fetch":
        verify_csrf(request, csrf_token)
    return _toggle_and_redirect(request, diary_id, "is_favorite", db, current_user, back)


@router.post("/diaries/{diary_id}/pin")
async def pin_diary(
    request: Request,
    diary_id: str,
    csrf_token: str = Form(default=""),
    back: str = Form("/diaries"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if request.headers.get("X-Requested-With") != "fetch":
        verify_csrf(request, csrf_token)
    return _toggle_and_redirect(request, diary_id, "is_pinned", db, current_user, back)


@router.post("/diaries/{diary_id}/archive")
async def archive_diary(
    request: Request,
    diary_id: str,
    csrf_token: str = Form(default=""),
    back: str = Form("/diaries"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if request.headers.get("X-Requested-With") != "fetch":
        verify_csrf(request, csrf_token)
    return _toggle_and_redirect(request, diary_id, "is_archived", db, current_user, back)


@router.post("/diaries/{diary_id}/restore")
def restore_diary(
    request: Request,
    diary_id: str,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    verify_csrf(request, csrf_token)
    diary = services.get_diary(db, current_user, diary_id)
    services.restore_diary(db, diary)
    return _redirect(f"/diaries/{diary_id}?msg=Entry+restored")


@router.post("/diaries/{diary_id}/duplicate")
def duplicate_diary(
    request: Request,
    diary_id: str,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    verify_csrf(request, csrf_token)
    diary = services.get_diary(db, current_user, diary_id)
    clone = services.duplicate_diary(db, diary)
    return _redirect(f"/diaries/{clone.id}?msg=Entry+duplicated")


@router.post("/diaries/{diary_id}/delete")
def delete_diary(
    request: Request,
    diary_id: str,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    verify_csrf(request, csrf_token)
    diary = services.get_diary(db, current_user, diary_id)
    services.delete_diary(db, diary)
    return _redirect("/diaries?msg=Entry+deleted")


# ──────────────────────────────────────────
# Export
# ──────────────────────────────────────────

def _safe_filename(title: str, ext: str) -> str:
    """Convert diary title to a safe filename."""
    safe = re.sub(r'[^\w\s-]', '', title).strip()
    safe = re.sub(r'[\s]+', '_', safe)[:60] or "diary"
    return f"{safe}.{ext}"


@router.get("/diaries/{diary_id}/export/json")
def export_json(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    if not current_user:
        return _redirect("/login")
    diary = services.get_diary(db, current_user, diary_id)
    data = {
        "id": diary.id,
        "title": diary.title,
        "content": diary.content,
        "mood": diary.mood,
        "visibility": diary.visibility,
        "tags": [t.name for t in diary.tags],
        "created_at": diary.created_at.isoformat(),
        "updated_at": diary.updated_at.isoformat(),
    }
    fname = _safe_filename(diary.title, "json")
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/diaries/{diary_id}/export/markdown")
def export_markdown(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    if not current_user:
        return _redirect("/login")
    diary = services.get_diary(db, current_user, diary_id)
    tags_str = ", ".join(t.name for t in diary.tags) if diary.tags else "—"
    md = (
        f"# {diary.title}\n\n"
        f"**Date:** {diary.created_at.strftime('%Y-%m-%d')}  \n"
        f"**Mood:** {diary.mood}  \n"
        f"**Tags:** {tags_str}\n\n"
        f"---\n\n"
        f"{diary.content}\n"
    )
    fname = _safe_filename(diary.title, "md")
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ──────────────────────────────────────────
# Search
# ──────────────────────────────────────────

@router.get("/search", response_class=HTMLResponse)
def search(
    request: Request,
    q: str | None = None,
    tag: str | None = None,
    mood: str | None = None,
    month: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    entries = services.list_diaries(db, current_user, search=q, tag=tag, mood=mood, month=month, year=year, archived=None)
    all_tags = repositories.list_tags(db, current_user.id)
    return _response_with_csrf(
        request,
        templates.TemplateResponse(
            request,
            "search.html",
            _base_context(request, current_user) | {
                "entries": entries,
                "query": q or "",
                "filters": {"tag": tag, "mood": mood, "month": month, "year": year},
                "all_tags": all_tags,
            },
        ),
    )


# ──────────────────────────────────────────
# Attachments
# ──────────────────────────────────────────

@router.post("/diaries/{diary_id}/attachments")
async def upload_attachment(
    request: Request,
    diary_id: str,
    file: UploadFile = File(default=None),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    from fastapi.responses import JSONResponse
    is_ajax = request.headers.get("X-Requested-With") == "fetch"
    if not current_user:
        if is_ajax:
            return JSONResponse({"ok": False, "detail": "Not authenticated"}, status_code=401)
        return _redirect("/login")
    # Validate file presence
    if not file or not file.filename:
        detail = "Please choose a file before uploading."
        if is_ajax:
            return JSONResponse({"ok": False, "detail": detail}, status_code=400)
        return _redirect(f"/diaries/{diary_id}?err={detail}")
    try:
        if not is_ajax:
            verify_csrf(request, csrf_token)
        diary = services.get_diary(db, current_user, diary_id)
        att = services.attach_file(db, current_user, diary, file)
        if is_ajax:
            return JSONResponse({
                "ok": True,
                "attachment": {
                    "id": att.id,
                    "filename": att.filename,
                    "size": att.size,
                    "mime_type": att.mime_type,
                },
            })
    except Exception as exc:
        if is_ajax:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=400)
        return _redirect(f"/diaries/{diary_id}?err={_safe_msg(exc)}")
    return _redirect(f"/diaries/{diary_id}?msg=File+uploaded")


# ──────────────────────────────────────────
# Settings
# ──────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db), current_user=Depends(get_optional_user)):
    if not current_user:
        return _redirect("/login")
    return _response_with_csrf(
        request,
        templates.TemplateResponse(request, "settings.html", _base_context(request, current_user)),
    )


@router.post("/settings/profile")
def update_profile(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        services.update_profile(db, current_user, UserUpdate(username=username, email=email))
    except Exception as exc:
        return _redirect(f"/settings?err={_safe_msg(exc)}")
    return _redirect("/settings?msg=Profile+updated")


@router.post("/settings/password")
def update_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        services.change_password(db, current_user, PasswordUpdate(current_password=current_password, new_password=new_password))
    except Exception as exc:
        return _redirect(f"/settings?err={_safe_msg(exc)}")
    return _redirect("/settings?msg=Password+changed")


@router.post("/settings/delete")
def delete_account(
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        services.delete_account(db, current_user)
    except Exception as exc:
        return _redirect(f"/settings?err={_safe_msg(exc)}")
    response = _redirect("/")
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


@router.post("/diaries/{diary_id}/bookmark")
async def bookmark_diary(
    request: Request,
    diary_id: str,
    csrf_token: str = Form(default=""),
    back: str = Form("/diaries"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if request.headers.get("X-Requested-With") != "fetch":
        verify_csrf(request, csrf_token)
    return _toggle_and_redirect(request, diary_id, "is_bookmarked", db, current_user, back)


@router.post("/diaries/{diary_id}/shares")
def web_share_diary(
    request: Request,
    diary_id: str,
    shared_to_username: str | None = Form(None),
    expires_in_hours: int | None = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        diary = services.get_diary(db, current_user, diary_id)
        if diary.user_id != current_user.id:
            return _redirect(f"/diaries/{diary_id}?err=Only the owner can share this entry")
            
        shared_to_user = None
        if shared_to_username and shared_to_username.strip():
            shared_to_user = repositories.get_user_by_username(db, shared_to_username.strip())
            if not shared_to_user:
                return _redirect(f"/diaries/{diary_id}?err=User to share with not found")
            if shared_to_user.id == current_user.id:
                return _redirect(f"/diaries/{diary_id}?err=You cannot share with yourself")
                
        expires_at = None
        if expires_in_hours:
            from datetime import timedelta
            expires_at = datetime.now(UTC) + timedelta(hours=expires_in_hours)
            
        from app.models import DiaryShare
        share = DiaryShare(
            diary_id=diary.id,
            shared_by_user_id=current_user.id,
            shared_to_user_id=shared_to_user.id if shared_to_user else None,
            expires_at=expires_at,
        )
        db.add(share)
        db.commit()
        return _redirect(f"/diaries/{diary_id}?msg=Shared+successfully")
    except Exception as exc:
        return _redirect(f"/diaries/{diary_id}?err={_safe_msg(exc)}")


@router.post("/diaries/{diary_id}/shares/{share_id}/revoke")
def web_revoke_share(
    request: Request,
    diary_id: str,
    share_id: str,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    try:
        verify_csrf(request, csrf_token)
        from app.models import DiaryShare
        share = db.get(DiaryShare, share_id)
        if not share or share.diary_id != diary_id:
            return _redirect(f"/diaries/{diary_id}?err=Share not found")
        if share.shared_by_user_id != current_user.id:
            return _redirect(f"/diaries/{diary_id}?err=Unauthorized")
        db.delete(share)
        db.commit()
        return _redirect(f"/diaries/{diary_id}?msg=Share revoked")
    except Exception as exc:
        return _redirect(f"/diaries/{diary_id}?err={_safe_msg(exc)}")


@router.get("/shared", response_class=HTMLResponse)
def shared_diaries_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    if not current_user:
        return _redirect("/login")
    from app.models import DiaryShare, Diary
    from sqlalchemy import select
    now = datetime.now(UTC)
    shares = db.scalars(
        select(DiaryShare)
        .where(
            DiaryShare.shared_to_user_id == current_user.id,
            (DiaryShare.expires_at == None) | (DiaryShare.expires_at > now)
        )
    ).all()
    
    public_diaries = db.scalars(
        select(Diary)
        .where(Diary.visibility == "public", Diary.user_id != current_user.id)
        .order_by(Diary.created_at.desc())
    ).all()
    
    return _response_with_csrf(
        request,
        templates.TemplateResponse(
            request,
            "shared_list.html",
            _base_context(request, current_user) | {
                "shares": shares,
                "public_diaries": public_diaries,
            }
        )
    )


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    from app.models import Attachment
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
        
    services.get_diary(db, current_user, attachment.diary_id)
    
    from fastapi.responses import FileResponse
    return FileResponse(
        attachment.path,
        filename=attachment.filename,
        media_type=attachment.mime_type
    )


@router.get("/attachments/{attachment_id}/view")
def view_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    from app.models import Attachment
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
        
    services.get_diary(db, current_user, attachment.diary_id)
    
    from fastapi.responses import FileResponse
    return FileResponse(
        attachment.path,
        media_type=attachment.mime_type
    )


# ──────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────

def _set_auth_cookies(response: RedirectResponse, access_token: str, refresh_token: str) -> None:
    response.set_cookie("access_token", access_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24)
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24 * 30)


def _safe_msg(exc: Exception) -> str:
    """Extract a safe, URL-encoded error message from an exception."""
    import urllib.parse
    msg = getattr(exc, "detail", None) or str(exc) or "An error occurred"
    return urllib.parse.quote(str(msg))
