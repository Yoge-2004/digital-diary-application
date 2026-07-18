from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from datetime import datetime, UTC
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app import repositories
from app.models import Attachment, Diary, Tag, User
from app.schemas import DiaryCreate, DiaryUpdate, PasswordUpdate, UserCreate, UserUpdate


def _normalize_tags(tags: Iterable[str] | None) -> list[str]:
    if not tags:
        return []
    return [tag.strip().lower() for tag in tags if tag and tag.strip()]


def split_tags(raw_tags: str | None) -> list[str]:
    if not raw_tags:
        return []
    return _normalize_tags(tag for tag in raw_tags.split(","))


def register_user(db: Session, payload: UserCreate) -> User:
    if repositories.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    if repositories.get_user_by_username(db, payload.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    return repositories.create_user(
        db,
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )


def authenticate_user(db: Session, identifier: str, password: str) -> User:
    user = repositories.get_user_by_email(db, identifier) or repositories.get_user_by_username(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    repositories.set_last_login(db, user)
    return user


def issue_tokens(user: User) -> tuple[str, str]:
    return create_access_token(user.id), create_refresh_token(user.id)


def get_user_or_404(db: Session, user_id: str) -> User:
    user = repositories.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def update_profile(db: Session, user: User, payload: UserUpdate) -> User:
    existing_email = repositories.get_user_by_email(db, payload.email)
    if existing_email and existing_email.id != user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    existing_username = repositories.get_user_by_username(db, payload.username)
    if existing_username and existing_username.id != user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    return repositories.update_user(db, user, username=payload.username, email=payload.email, profile_image=payload.profile_image)


def change_password(db: Session, user: User, payload: PasswordUpdate) -> User:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    return repositories.update_user_password(db, user, hash_password(payload.new_password))


def delete_account(db: Session, user: User) -> None:
    repositories.delete_user(db, user)


def verify_reset_credentials(db: Session, username: str, email: str) -> User | None:
    """Return user if both username and email match a single account, else None."""
    user = repositories.get_user_by_username(db, username)
    if user and user.email.lower() == email.strip().lower():
        return user
    return None


def reset_password_by_credentials(db: Session, username: str, email: str, new_password: str) -> bool:
    """Reset password if credentials match. Returns True on success."""
    user = verify_reset_credentials(db, username, email)
    if not user:
        return False
    repositories.update_user_password(db, user, hash_password(new_password))
    return True


def create_diary(db: Session, user: User, payload: DiaryCreate) -> Diary:
    return repositories.create_diary(
        db,
        user.id,
        title=payload.title,
        content=payload.content,
        mood=payload.mood,
        visibility=payload.visibility,
        location=payload.location,
        tag_names=_normalize_tags(payload.tags),
    )


def edit_diary(db: Session, diary: Diary, payload: DiaryUpdate) -> Diary:
    return repositories.update_diary(
        db,
        diary,
        title=payload.title,
        content=payload.content,
        mood=payload.mood,
        visibility=payload.visibility,
        location=payload.location,
        tag_names=_normalize_tags(payload.tags) if payload.tags is not None else None,
        is_archived=payload.is_archived,
        is_favorite=payload.is_favorite,
        is_pinned=payload.is_pinned,
        is_bookmarked=payload.is_bookmarked,
    )


def toggle_flag(db: Session, diary: Diary, field: str) -> Diary:
    if field == "is_favorite":
        diary.is_favorite = not diary.is_favorite
    elif field == "is_pinned":
        diary.is_pinned = not diary.is_pinned
    elif field == "is_archived":
        diary.is_archived = not diary.is_archived
    elif field == "is_bookmarked":
        diary.is_bookmarked = not diary.is_bookmarked
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid flag")
    db.commit()
    db.refresh(diary)
    return diary


def restore_diary(db: Session, diary: Diary) -> Diary:
    diary.is_archived = False
    db.commit()
    db.refresh(diary)
    return diary


def duplicate_diary(db: Session, diary: Diary) -> Diary:
    return repositories.duplicate_diary(db, diary)


def delete_diary(db: Session, diary: Diary) -> None:
    repositories.delete_diary(db, diary)


def list_diaries(db: Session, user: User, **filters):
    return repositories.list_diaries(db, user.id, **filters)


def diary_summary(db: Session, user: User) -> dict:
    return repositories.diary_statistics(db, user.id)


def get_diary(db: Session, user: User | None, diary_id: str) -> Diary:
    diary = repositories.get_diary_by_id(db, diary_id)
    if not diary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diary not found")
    
    # Owner always has access
    if user and diary.user_id == user.id:
        return diary
        
    # Public visibility always has access
    if diary.visibility == "public":
        return diary
        
    # Check share permissions
    from sqlalchemy import select
    from app.models import DiaryShare
    
    now = datetime.now(UTC)
    shares = db.scalars(select(DiaryShare).where(DiaryShare.diary_id == diary.id)).all()
    for share in shares:
        if share.expires_at:
            # Safely make comparisons tz-naive or tz-aware depending on SQLite vs Postgres
            s_exp = share.expires_at.replace(tzinfo=None) if share.expires_at.tzinfo else share.expires_at
            now_cmp = now.replace(tzinfo=None) if now.tzinfo else now
            if s_exp < now_cmp:
                continue
        if share.shared_to_user_id is None:
            # Public share link
            return diary
        if user and share.shared_to_user_id == user.id:
            # Shared directly to user
            return diary

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")




def get_tag(db: Session, user: User, tag_id: str) -> Tag:
    tag = repositories.get_tag(db, user.id, tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


def get_attachment(db: Session, user: User, attachment_id: str) -> Attachment:
    attachment = repositories.get_attachment(db, user.id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment


def list_tags(db: Session, user: User) -> list[Tag]:
    return repositories.list_tags(db, user.id)


def delete_tag(db: Session, tag: Tag) -> None:
    repositories.delete_tag(db, tag)


def attach_file(db: Session, user: User, diary: Diary, file: UploadFile) -> Attachment:
    filename = f"{diary.id}-{file.filename or 'attachment'}"
    target = settings.upload_dir / filename
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    target.write_bytes(data)
    return repositories.add_attachment(
        db,
        diary=diary,
        user_id=user.id,
        filename=file.filename or "attachment",
        path=str(target),
        mime_type=file.content_type or "application/octet-stream",
        size=len(data),
    )


def remove_attachment(db: Session, attachment: Attachment) -> None:
    path = Path(attachment.path)
    if path.exists():
        path.unlink()
    repositories.delete_attachment(db, attachment)
