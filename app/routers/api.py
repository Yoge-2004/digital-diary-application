from __future__ import annotations

from datetime import datetime, UTC
from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, Response, UploadFile, status
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


router = APIRouter(prefix="/api", tags=["api"])



@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(response: Response, payload: UserCreate, db: Session = Depends(get_db)):
    user = services.register_user(db, payload)
    access_token, refresh_token = services.issue_tokens(user)
    response.set_cookie("access_token", access_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24)
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24 * 30)
    return user


@router.post("/auth/login", response_model=AuthToken)
def login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = services.authenticate_user(db, username, password)
    access_token, refresh_token = services.issue_tokens(user)
    response.set_cookie("access_token", access_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24)
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=60 * 60 * 24 * 30)
    return AuthToken(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/logout", response_model=APIMessage)
def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return APIMessage(message="Logged out")


@router.post("/auth/refresh", response_model=AuthToken)
def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias="refresh_token")):
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


@router.get("/users/me", response_model=UserRead)
def me(current_user=Depends(get_current_user)):
    return current_user


@router.put("/users/me", response_model=UserRead)
def update_me(payload: UserUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return services.update_profile(db, current_user, payload)


@router.delete("/users/me", response_model=APIMessage)
def delete_me(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    services.delete_account(db, current_user)
    return APIMessage(message="Account deleted")


@router.get("/diaries", response_model=list[DiaryRead])
def list_diaries(
    search: str | None = None,
    tag: str | None = None,
    mood: str | None = None,
    favorite: bool | None = None,
    archived: bool | None = None,
    month: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
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


@router.post("/diaries", response_model=DiaryRead, status_code=status.HTTP_201_CREATED)
def create_diary(payload: DiaryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.create_diary(db, current_user, payload)
    return diary


@router.get("/diaries/{diary_id}", response_model=DiaryRead)
def get_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return services.get_diary(db, current_user, diary_id)


@router.put("/diaries/{diary_id}", response_model=DiaryRead)
def update_diary(diary_id: str, payload: DiaryUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.get_diary(db, current_user, diary_id)
    return services.edit_diary(db, diary, payload)


@router.delete("/diaries/{diary_id}", response_model=APIMessage)
def delete_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.get_diary(db, current_user, diary_id)
    services.delete_diary(db, diary)
    return APIMessage(message="Diary deleted")


@router.patch("/diaries/{diary_id}/favorite", response_model=DiaryRead)
def favorite_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.get_diary(db, current_user, diary_id)
    return services.toggle_flag(db, diary, "is_favorite")


@router.patch("/diaries/{diary_id}/pin", response_model=DiaryRead)
def pin_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.get_diary(db, current_user, diary_id)
    return services.toggle_flag(db, diary, "is_pinned")


@router.patch("/diaries/{diary_id}/archive", response_model=DiaryRead)
def archive_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.get_diary(db, current_user, diary_id)
    return services.toggle_flag(db, diary, "is_archived")


@router.patch("/diaries/{diary_id}/bookmark", response_model=DiaryRead)
def bookmark_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.get_diary(db, current_user, diary_id)
    return services.toggle_flag(db, diary, "is_bookmarked")


@router.patch("/diaries/{diary_id}/restore", response_model=DiaryRead)
def restore_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.get_diary(db, current_user, diary_id)
    return services.restore_diary(db, diary)


@router.post("/diaries/{diary_id}/duplicate", response_model=DiaryRead, status_code=status.HTTP_201_CREATED)
def duplicate_diary(diary_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    diary = services.get_diary(db, current_user, diary_id)
    return services.duplicate_diary(db, diary)


@router.post("/diaries/{diary_id}/shares", response_model=DiaryShareRead, status_code=status.HTTP_201_CREATED)
def share_diary(
    diary_id: str,
    payload: DiaryShareCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Verify owner
    diary = services.get_diary(db, current_user, diary_id)
    if diary.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can share this entry")
        
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



@router.get("/tags", response_model=list[TagRead])
def list_tags(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return services.list_tags(db, current_user)


@router.delete("/tags/{tag_id}", response_model=APIMessage)
def delete_tag(tag_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    tag = services.get_tag(db, current_user, tag_id)
    services.delete_tag(db, tag)
    return APIMessage(message="Tag deleted")


@router.post("/diaries/{diary_id}/attachments", status_code=status.HTTP_201_CREATED, response_model=APIMessage)
def upload_attachment(
    diary_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    diary = services.get_diary(db, current_user, diary_id)
    services.attach_file(db, current_user, diary, file)
    return APIMessage(message="Attachment uploaded")


@router.delete("/attachments/{attachment_id}", response_model=APIMessage)
def delete_attachment(attachment_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    attachment = services.get_attachment(db, current_user, attachment_id)
    services.remove_attachment(db, attachment)
    return APIMessage(message="Attachment deleted")


@router.get("/stats/dashboard", response_model=DiarySummary)
def dashboard_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
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
