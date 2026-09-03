from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def uuid_str() -> str:
    return uuid4().hex


diary_tags = Table(
    "diary_tags",
    Base.metadata,
    Column("diary_id", String(32), ForeignKey("diaries.id"), primary_key=True),
    Column("tag_id", String(32), ForeignKey("tags.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    profile_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # OAuth (e.g. "google"). NULL/NULL for password-only accounts. An
    # account can currently be linked to at most one external provider;
    # password_hash stays NOT NULL even for OAuth-only signups (see
    # services.get_or_create_oauth_user) rather than making the column
    # nullable, since this app has no real migration tooling and altering
    # an existing column's nullability isn't something patch_missing_columns
    # (additive-only) can do safely on SQLite.
    oauth_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Email verification (OTP-style: a short numeric code, not a link).
    # email_verified defaults to None/falsy for both pre-existing accounts
    # (backfilled by patch_missing_columns with NULL, since it can't apply
    # an ORM-level default retroactively) and brand-new ones -- this is
    # intentionally never used to block login or any feature; it only
    # drives a dismissible-until-verified reminder banner. Gating real
    # functionality on it would lock out every account that existed
    # before this column did.
    email_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verification_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    verification_code_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Daily "write today" reminder, delivered via Web Push (see
    # PushSubscription below and app/core/push.py). All three are
    # nullable for the same additive-migration reason as email_verified
    # above -- patch_missing_columns can only add nullable columns to an
    # existing table, so any column a pre-existing account needs a real
    # default for has to tolerate NULL and resolve the "off" state in
    # Python, not in the schema.
    #   reminder_enabled: None/False = off (the default for every
    #     existing account when this column first appears, and for new
    #     signups until they opt in -- this is a notification permission,
    #     never on by default).
    #   reminder_time: "HH:MM" 24-hour local time, e.g. "20:00".
    #   reminder_timezone: IANA name (e.g. "America/Chicago"), captured
    #     client-side via Intl.DateTimeFormat().resolvedOptions().timeZone
    #     when they opt in -- a server has no reliable way to know a
    #     browser's timezone otherwise, and guessing wrong would mean the
    #     reminder fires at the wrong local time.
    #   last_reminder_sent_on: the local calendar date (YYYY-MM-DD, as a
    #     string) the reminder scheduler last actually sent a push for.
    #     Exists purely to make each day's reminder idempotent -- the
    #     scheduler loop runs every minute and must not re-send if it
    #     happens to see the same due minute twice, or re-send later the
    #     same day after a server restart.
    reminder_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reminder_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    reminder_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_reminder_sent_on: Mapped[str | None] = mapped_column(String(10), nullable=True)

    diaries: Mapped[list["Diary"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Diary(Base):
    __tablename__ = "diaries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[str] = mapped_column(Text)
    mood: Mapped[str] = mapped_column(String(50), default="neutral", index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    user: Mapped[User] = relationship(back_populates="diaries")
    tags: Mapped[list["Tag"]] = relationship(secondary=diary_tags, back_populates="diaries")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="diary", cascade="all, delete-orphan")
    shares: Mapped[list["DiaryShare"]] = relationship(back_populates="diary", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tags_user_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)

    user: Mapped[User] = relationship(back_populates="tags")
    diaries: Mapped[list[Diary]] = relationship(secondary=diary_tags, back_populates="tags")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    diary_id: Mapped[str] = mapped_column(ForeignKey("diaries.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    diary: Mapped[Diary] = relationship(back_populates="attachments")
    user: Mapped[User] = relationship(back_populates="attachments")


class DiaryShare(Base):
    __tablename__ = "diary_shares"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    diary_id: Mapped[str] = mapped_column(ForeignKey("diaries.id", ondelete="CASCADE"), index=True)
    shared_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shared_to_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    diary: Mapped[Diary] = relationship(back_populates="shares")
    shared_by: Mapped[User] = relationship(foreign_keys=[shared_by_user_id])
    shared_to: Mapped[User | None] = relationship(foreign_keys=[shared_to_user_id])


class PushSubscription(Base):
    """One browser/device subscribed to Web Push for a user's daily
    reminder. A user can have several of these (phone + laptop, or two
    browsers) -- each is delivered to independently, and each is removed
    independently if the push service reports it's gone stale (see
    app/core/push.py, which handles the 404/410 "subscription expired"
    response by deleting the row rather than retrying forever)."""

    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user: Mapped[User] = relationship(back_populates="push_subscriptions")

    __table_args__ = (UniqueConstraint("user_id", "endpoint", name="uq_push_subscription_user_endpoint"),)
