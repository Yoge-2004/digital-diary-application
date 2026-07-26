from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, desc, extract, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Attachment, Diary, Tag, User


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username.lower()))


def create_user(db: Session, username: str, email: str, password_hash: str) -> User:
    user = User(username=username.lower().strip(), email=email.lower().strip(), password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, *, username: str, email: str, profile_image: str | None = None) -> User:
    user.username = username.lower().strip()
    user.email = email.lower().strip()
    if profile_image is not None:
        user.profile_image = profile_image
    db.commit()
    db.refresh(user)
    return user


def update_user_password(db: Session, user: User, password_hash: str) -> User:
    user.password_hash = password_hash
    db.commit()
    db.refresh(user)
    return user


def set_password_reset_token(db: Session, user: User, token: str | None, expires_at) -> User:
    user.reset_token = token
    user.reset_token_expires = expires_at
    db.commit()
    db.refresh(user)
    return user


def get_user_by_reset_token(db: Session, token: str) -> User | None:
    return db.scalar(select(User).where(User.reset_token == token))


def set_last_login(db: Session, user: User) -> User:
    user.last_login = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()


def get_or_create_tag(db: Session, user_id: str, name: str) -> Tag:
    normalized = name.strip().lower()
    tag = db.scalar(select(Tag).where(Tag.user_id == user_id, Tag.name == normalized))
    if tag:
        return tag
    tag = Tag(user_id=user_id, name=normalized)
    db.add(tag)
    db.flush()
    return tag


def list_tags(db: Session, user_id: str) -> list[Tag]:
    return list(db.scalars(select(Tag).where(Tag.user_id == user_id).order_by(Tag.name)))


def get_tag(db: Session, user_id: str, tag_id: str) -> Tag | None:
    return db.scalar(select(Tag).where(Tag.user_id == user_id, Tag.id == tag_id))


def get_attachment(db: Session, user_id: str, attachment_id: str) -> Attachment | None:
    return db.scalar(select(Attachment).where(Attachment.user_id == user_id, Attachment.id == attachment_id))


def delete_tag(db: Session, tag: Tag) -> None:
    db.delete(tag)
    db.commit()


def _base_diary_query(user_id: str):
    return select(Diary).where(Diary.user_id == user_id).options(
        selectinload(Diary.tags), selectinload(Diary.attachments)
    )


def get_diary(db: Session, user_id: str, diary_id: str) -> Diary | None:
    return db.scalar(_base_diary_query(user_id).where(Diary.id == diary_id))


def get_diary_by_id(db: Session, diary_id: str) -> Diary | None:
    return db.scalar(
        select(Diary)
        .where(Diary.id == diary_id)
        .options(selectinload(Diary.tags), selectinload(Diary.attachments))
    )



def list_diaries(
    db: Session,
    user_id: str,
    *,
    search: str | None = None,
    tag: str | None = None,
    mood: str | None = None,
    favorite: bool | None = None,
    bookmarked: bool | None = None,
    archived: bool | None = False,   # default: hide archived
    month: int | None = None,
    year: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Diary]:
    query = _base_diary_query(user_id)
    conditions: list[Any] = []
    if search:
        like = f"%{search.strip()}%"
        conditions.append((Diary.title.ilike(like)) | (Diary.content.ilike(like)) | (Diary.location.ilike(like)))
    if mood:
        conditions.append(Diary.mood == mood)
    if favorite is not None:
        conditions.append(Diary.is_favorite.is_(favorite))
    if bookmarked is not None:
        conditions.append(Diary.is_bookmarked.is_(bookmarked))
    if archived is not None:
        conditions.append(Diary.is_archived.is_(archived))
    if month is not None:
        conditions.append(extract("month", Diary.created_at) == month)
    if year is not None:
        conditions.append(extract("year", Diary.created_at) == year)
    if tag:
        query = query.join(Diary.tags).where(Tag.name == tag.strip().lower())
    if conditions:
        query = query.where(and_(*conditions))
    if tag:
        query = query.distinct()
    query = query.order_by(desc(Diary.is_pinned), desc(Diary.updated_at), desc(Diary.created_at))
    return list(db.scalars(query.limit(limit).offset(offset)))



def count_diaries(db: Session, user_id: str) -> int:
    return db.scalar(select(func.count()).select_from(Diary).where(Diary.user_id == user_id)) or 0


def create_diary(
    db: Session,
    user_id: str,
    *,
    title: str,
    content: str,
    mood: str,
    visibility: str,
    location: str | None = None,
    tag_names: list[str],
    created_at=None,
) -> Diary:
    diary = Diary(
        user_id=user_id,
        title=title.strip(),
        content=content.strip(),
        mood=mood,
        visibility=visibility,
        location=location.strip() if location else None,
    )
    if created_at is not None:
        diary.created_at = created_at
    diary.tags = [get_or_create_tag(db, user_id, name) for name in tag_names if name.strip()]
    db.add(diary)
    db.commit()
    db.refresh(diary)
    return diary


def update_diary(
    db: Session,
    diary: Diary,
    *,
    title: str | None = None,
    content: str | None = None,
    mood: str | None = None,
    visibility: str | None = None,
    location: str | None = None,
    tag_names: list[str] | None = None,
    created_at=None,
    is_archived: bool | None = None,
    is_favorite: bool | None = None,
    is_pinned: bool | None = None,
    is_bookmarked: bool | None = None,
) -> Diary:
    if title is not None:
        diary.title = title.strip()
    if content is not None:
        diary.content = content.strip()
    if mood is not None:
        diary.mood = mood
    if visibility is not None:
        diary.visibility = visibility
    if location is not None:
        diary.location = location.strip() if location else None
    if created_at is not None:
        diary.created_at = created_at
    if tag_names is not None:
        diary.tags = [get_or_create_tag(db, diary.user_id, name) for name in tag_names if name.strip()]
    if is_archived is not None:
        diary.is_archived = is_archived
    if is_favorite is not None:
        diary.is_favorite = is_favorite
    if is_pinned is not None:
        diary.is_pinned = is_pinned
    if is_bookmarked is not None:
        diary.is_bookmarked = is_bookmarked
    db.commit()
    db.refresh(diary)
    return diary


def delete_diary(db: Session, diary: Diary) -> None:
    db.delete(diary)
    db.commit()


def duplicate_diary(db: Session, diary: Diary) -> Diary:
    clone = Diary(
        user_id=diary.user_id,
        title=f"{diary.title} (copy)",
        content=diary.content,
        mood=diary.mood,
        visibility=diary.visibility,
        location=diary.location,
        is_archived=False,
        is_favorite=False,
        is_pinned=False,
        is_bookmarked=False,
    )
    clone.tags = list(diary.tags)
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone



def add_attachment(
    db: Session,
    *,
    diary: Diary,
    user_id: str,
    filename: str,
    path: str,
    mime_type: str,
    size: int,
) -> Attachment:
    attachment = Attachment(
        diary_id=diary.id,
        user_id=user_id,
        filename=filename,
        path=path,
        mime_type=mime_type,
        size=size,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def delete_attachment(db: Session, attachment: Attachment) -> None:
    db.delete(attachment)
    db.commit()


def list_dates(db: Session, user_id: str) -> list[date]:
    rows = db.scalars(select(Diary.created_at).where(Diary.user_id == user_id, Diary.is_archived.is_(False)))
    return [row.date() for row in rows if row]


def list_diaries_for_calendar(db: Session, user_id: str, year: int, month: int) -> list[Diary]:
    """Return all non-archived diaries for a given year/month, minimal load."""
    return list(db.scalars(
        select(Diary)
        .where(
            Diary.user_id == user_id,
            Diary.is_archived.is_(False),
            extract("year", Diary.created_at) == year,
            extract("month", Diary.created_at) == month,
        )
        .options(selectinload(Diary.tags))
        .order_by(Diary.created_at)
    ))


def diary_statistics(db: Session, user_id: str) -> dict[str, Any]:
    diaries = list(db.scalars(select(Diary).where(Diary.user_id == user_id).order_by(Diary.created_at.desc())))
    total_entries = len(diaries)
    favorites = sum(1 for diary in diaries if diary.is_favorite)
    archive_count = sum(1 for diary in diaries if diary.is_archived)
    mood_distribution = dict(Counter(diary.mood for diary in diaries))
    created_dates = sorted({diary.created_at.date() for diary in diaries}, reverse=True)
    current_streak = _calculate_current_streak(created_dates)
    longest_streak = _calculate_longest_streak(created_dates)
    now = datetime.now(UTC)
    monthly_entries = sum(1 for diary in diaries if diary.created_at.month == now.month and diary.created_at.year == now.year)
    recent_diaries = [d for d in diaries if not d.is_archived][:5]

    # monthly activity for the past 12 months
    monthly_activity: dict[str, int] = {}
    for d in diaries:
        key = d.created_at.strftime("%Y-%m")
        monthly_activity[key] = monthly_activity.get(key, 0) + 1

    # day-of-week activity
    dow_activity: dict[str, int] = {day: 0 for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
    for d in diaries:
        dow = d.created_at.strftime("%a")
        dow_activity[dow] = dow_activity.get(dow, 0) + 1

    return {
        "total_entries": total_entries,
        "favorites": favorites,
        "archive_count": archive_count,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "monthly_entries": monthly_entries,
        "mood_distribution": mood_distribution,
        "recent_diaries": recent_diaries,
        "monthly_activity": monthly_activity,
        "dow_activity": dow_activity,
    }


def _calculate_current_streak(dates: list[date]) -> int:
    if not dates:
        return 0
    date_set = set(dates)
    cursor = date.today()
    streak = 0
    while cursor in date_set:
        streak += 1
        cursor = cursor.fromordinal(cursor.toordinal() - 1)
    return streak


def _calculate_longest_streak(dates: list[date]) -> int:
    if not dates:
        return 0
    ordered = sorted(set(dates))
    longest = 1
    current = 1
    for previous, today in zip(ordered, ordered[1:]):
        if today.toordinal() - previous.toordinal() == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest
