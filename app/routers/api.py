from __future__ import annotations

from datetime import datetime, UTC
from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app import services, repositories
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.deps import get_current_user
from app.db.session import get_db
from app.schemas import (
    APIMessage,
    AuthToken,
    DiaryCreate,
    DiaryRead,
    DiarySummary,
    DiaryUpdate,
    TagRead,
    UserCreate,
    UserRead,
    UserUpdate,
    DiaryShareCreate,
    DiaryShareRead,
)


router = APIRouter(prefix="/api")


@router.post(
    "/auth/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
    summary="Create an account",
    description="Registers a new user and immediately signs them in, setting the "
    "access_token and refresh_token cookies on the response.",
)
def register(request: Request, response: Response, payload: UserCreate, db: Session = Depends(get_db)):
    """Register a new user and log them in via httponly cookies."""
    user = services.register_user(db, payload)
    if request.app.state.settings.email_service_enabled:
        try:
            services.send_verification_code(db, user)
        except Exception:
            pass  # never let a flaky SMTP server block registration itself
    access_token, refresh_token = services.issue_tokens(user)
    response.set_cookie("access_token", access_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24)
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24 * 30)
    return user


@router.post(
    "/auth/login",
    response_model=AuthToken,
    tags=["Authentication"],
    summary="Sign in",
    description="Exchanges a username + password for an access/refresh token pair. "
    "The same tokens are also set as httponly cookies for browser clients.",
)
def login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Authenticate a user by username + password and issue new tokens."""
    user = services.authenticate_user(db, username, password)
    access_token, refresh_token = services.issue_tokens(user)
    response.set_cookie("access_token", access_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24)
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24 * 30)
    return AuthToken(access_token=access_token, refresh_token=refresh_token)


@router.post(
    "/auth/logout",
    response_model=APIMessage,
    tags=["Authentication"],
    summary="Sign out",
    description="Clears the access_token and refresh_token cookies. Does not "
    "invalidate the tokens server-side (they are stateless JWTs), so a client "
    "that already captured them could still use them until they expire.",
)
def logout(response: Response):
    """Clear auth cookies on the response."""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return APIMessage(message="Logged out")


@router.post(
    "/auth/refresh",
    response_model=AuthToken,
    tags=["Authentication"],
    summary="Refresh an access token",
    description="Trades a valid refresh_token cookie for a brand new access/refresh pair.",
)
def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias="refresh_token")):
    """Issue a new token pair from a still-valid refresh token cookie."""
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        user_id = decode_token(refresh_token, "refresh")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    access_token = create_access_token(user_id)
    new_refresh_token = create_refresh_token(user_id)
    response.set_cookie("access_token", access_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24)
    response.set_cookie("refresh_token", new_refresh_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24 * 30)
    return AuthToken(access_token=access_token, refresh_token=new_refresh_token)


@router.get("/users/me", response_model=UserRead, tags=["Users"], summary="Get the signed-in user's profile")
def me(current_user=Depends(get_current_user)):
    """Return the currently authenticated user."""
    return current_user


@router.put("/users/me", response_model=UserRead, tags=["Users"], summary="Update the signed-in user's profile")
def update_me(payload: UserUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Update the current user's username/email/profile image."""
    return services.update_profile(db, current_user, payload)


@router.delete(
    "/users/me",
    response_model=APIMessage,
    tags=["Users"],
    summary="Delete the signed-in user's account",
    description="Permanently deletes the account and, via cascade, every diary, "
    "tag, and attachment it owns. This cannot be undone.",
)
def delete_me(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Permanently delete the current user's account and all owned data."""
    services.delete_account(db, current_user)
    return APIMessage(message="Account deleted")


@router.get(
    "/diaries",
    response_model=list[DiaryRead],
    tags=["Diaries"],
    summary="List your diary entries",
    description="Returns the current user's own entries, optionally filtered by "
    "free-text search, tag name, mood, favourite/archived state, or a given "
    "month + year. Does not include other users' public or shared entries — "
    "see GET /shared (web) for those.",
)
def list_diaries(
    search: str | None = None,
    tag: str | None = None,
    mood: str | None = None,
    favorite: bool | None = None,
    archived: bool = False,
    month: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List the current user's diaries with optional filters. `archived`
    defaults to False (hidden), matching the web /diaries list."""
    return services.list_diaries(
        db,
        current_user,
        search=search,
        tag=tag,
        mood=mood,
        favorite=favorite,
        archived=archived,
        month=month,
        year=year,
    )


@router.post(
    "/diaries",
    response_model=DiaryRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Diaries"],
    summary="Create a diary entry",
    description="Creates a new entry owned by the current user. `visibility` is "
    "'private' (default) or 'public'; `location` is a free-text place name "
    "(e.g. from reverse geocoding on the client) and is optional.",
)
def create_diary(payload: DiaryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Create a new diary entry for the current user."""
    diary = services.create_diary(db, current_user, payload)
    return diary


@router.get(
    "/diaries/{diary_id}",
    response_model=DiaryRead,
    tags=["Diaries"],
    summary="Get a single diary entry",
    description="Viewable by the owner, by anyone if `visibility` is 'public', "
    "or by a user the entry has been shared with (see POST /diaries/{id}/shares).",
)
def get_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Fetch one diary entry the current user is allowed to view."""
    return services.get_diary(db, current_user, diary_id)


@router.put(
    "/diaries/{diary_id}",
    response_model=DiaryRead,
    tags=["Diaries"],
    summary="Edit a diary entry",
    description="Owner-only. Viewing access via public visibility or a share "
    "does not grant edit rights.",
)
def update_diary(diary_id: str, payload: DiaryUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Update a diary entry. Raises 403 if the caller isn't the owner."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    return services.edit_diary(db, diary, payload)


@router.delete(
    "/diaries/{diary_id}",
    response_model=APIMessage,
    tags=["Diaries"],
    summary="Delete a diary entry",
    description="Owner-only and permanent — also removes the entry's attachments "
    "and shares via cascade.",
)
def delete_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Delete a diary entry. Raises 403 if the caller isn't the owner."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    services.delete_diary(db, diary)
    return APIMessage(message="Diary deleted")


@router.patch(
    "/diaries/{diary_id}/favorite",
    response_model=DiaryRead,
    tags=["Diaries"],
    summary="Toggle favourite",
    description="Owner-only. Flips `is_favorite` and returns the updated entry.",
)
def favorite_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Toggle the is_favorite flag on an owned diary."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    return services.toggle_flag(db, diary, "is_favorite")


@router.patch(
    "/diaries/{diary_id}/pin",
    response_model=DiaryRead,
    tags=["Diaries"],
    summary="Toggle pinned",
    description="Owner-only. Flips `is_pinned` — pinned entries are meant to "
    "surface at the top of the dashboard/list views.",
)
def pin_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Toggle the is_pinned flag on an owned diary."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    return services.toggle_flag(db, diary, "is_pinned")


@router.patch(
    "/diaries/{diary_id}/archive",
    response_model=DiaryRead,
    tags=["Diaries"],
    summary="Toggle archived",
    description="Owner-only. Flips `is_archived`; archived entries are excluded "
    "from the default diary list. Use the /restore endpoint to bring one back.",
)
def archive_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Toggle the is_archived flag on an owned diary."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    return services.toggle_flag(db, diary, "is_archived")


@router.patch(
    "/diaries/{diary_id}/bookmark",
    response_model=DiaryRead,
    tags=["Diaries"],
    summary="Toggle bookmarked",
    description="Owner-only. Flips `is_bookmarked`, a separate marker from "
    "`is_favorite` intended for a 'read again later' list.",
)
def bookmark_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Toggle the is_bookmarked flag on an owned diary."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    return services.toggle_flag(db, diary, "is_bookmarked")


@router.patch(
    "/diaries/{diary_id}/restore",
    response_model=DiaryRead,
    tags=["Diaries"],
    summary="Restore an archived entry",
    description="Owner-only. Sets `is_archived` back to false.",
)
def restore_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Un-archive an owned diary entry."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    return services.restore_diary(db, diary)


@router.post(
    "/diaries/{diary_id}/duplicate",
    response_model=DiaryRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Diaries"],
    summary="Duplicate an entry",
    description="Owner-only. Creates a copy titled '<original> (copy)' with "
    "favourite/pinned/archived/bookmarked reset to false.",
)
def duplicate_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Duplicate an owned diary entry into a new entry."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    return services.duplicate_diary(db, diary)


@router.post(
    "/diaries/{diary_id}/shares",
    response_model=DiaryShareRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Sharing"],
    summary="Share an entry",
    description="Owner-only. Share with a specific user by username, or omit "
    "`shared_to_username` to create a public share link anyone can use. "
    "`expires_in_hours` is optional; omit it for a share that never expires.",
)
def share_diary(
    diary_id: str,
    payload: DiaryShareCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a share (targeted at a user, or a public link) for an owned diary."""
    diary = services.get_owned_diary(db, current_user, diary_id)

    shared_to_user = None
    if payload.shared_to_username:
        shared_to_user = repositories.get_user_by_username(db, payload.shared_to_username)
        if not shared_to_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to share with not found")
        if shared_to_user.id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot share with yourself")
            
    expires_at = None
    if payload.expires_in_hours:
        from datetime import timedelta
        expires_at = datetime.now(UTC) + timedelta(hours=payload.expires_in_hours)
        
    from app.models import DiaryShare
    share = DiaryShare(
        diary_id=diary.id,
        shared_by_user_id=current_user.id,
        shared_to_user_id=shared_to_user.id if shared_to_user else None,
        expires_at=expires_at,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    
    ret = DiaryShareRead.model_validate(share)
    if shared_to_user:
        ret.shared_to_username = shared_to_user.username
    return ret


@router.get("/tags", response_model=list[TagRead], tags=["Tags"], summary="List your tags")
def list_tags(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """List every tag the current user has used across their diaries."""
    return services.list_tags(db, current_user)


@router.delete(
    "/tags/{tag_id}",
    response_model=APIMessage,
    tags=["Tags"],
    summary="Delete a tag",
    description="Owner-only. Removes the tag from all of the user's diaries "
    "that reference it; the diaries themselves are not deleted.",
)
def delete_tag(tag_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Delete a tag owned by the current user."""
    tag = services.get_tag(db, current_user, tag_id)
    services.delete_tag(db, tag)
    return APIMessage(message="Tag deleted")


@router.post(
    "/diaries/{diary_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=APIMessage,
    tags=["Attachments"],
    summary="Upload an attachment",
    description="Owner-only. Attaches a file (image, PDF, etc.) to a diary "
    "entry. Uploaded files are served back via GET /attachments/{id}/view "
    "(inline) or /attachments/{id}/download.",
)
def upload_attachment(
    request: Request,
    diary_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Upload and attach a file to an owned diary entry."""
    diary = services.get_owned_diary(db, current_user, diary_id)
    services.attach_file(db, current_user, diary, file, upload_dir=request.app.state.settings.upload_dir)
    return APIMessage(message="Attachment uploaded")


@router.delete(
    "/attachments/{attachment_id}",
    response_model=APIMessage,
    tags=["Attachments"],
    summary="Delete an attachment",
    description="Only the user who uploaded the attachment can delete it.",
)
def delete_attachment(attachment_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Delete an attachment uploaded by the current user."""
    attachment = services.get_attachment(db, current_user, attachment_id)
    services.remove_attachment(db, attachment)
    return APIMessage(message="Attachment deleted")


@router.get(
    "/stats/dashboard",
    response_model=DiarySummary,
    tags=["Statistics"],
    summary="Dashboard summary",
    description="Aggregate counts and streaks for the current user: total "
    "entries, favourites, archived count, current/longest writing streak, "
    "entries per month, mood distribution, and the most recent entries.",
)
def dashboard_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Return aggregate diary statistics for the current user."""
    summary = services.diary_summary(db, current_user)
    return DiarySummary(
        total_entries=summary["total_entries"],
        favorites=summary["favorites"],
        archive_count=summary["archive_count"],
        current_streak=summary["current_streak"],
        longest_streak=summary["longest_streak"],
        monthly_entries=summary["monthly_entries"],
        mood_distribution=summary["mood_distribution"],
        recent_diaries=summary["recent_diaries"],
    )
