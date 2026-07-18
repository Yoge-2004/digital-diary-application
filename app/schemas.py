from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class APIMessage(BaseModel):
    message: str


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    profile_image: str | None = None


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_image: str | None = None
    created_at: datetime
    last_login: datetime | None = None


class AuthToken(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class DiaryBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    mood: str = Field(default="neutral", max_length=50)
    visibility: str = Field(default="private", max_length=20)
    location: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list)


class DiaryCreate(DiaryBase):
    pass


class DiaryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    mood: str | None = Field(default=None, max_length=50)
    visibility: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    is_archived: bool | None = None
    is_favorite: bool | None = None
    is_pinned: bool | None = None
    is_bookmarked: bool | None = None


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    path: str
    mime_type: str
    size: int
    created_at: datetime


class DiaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    content: str
    mood: str
    visibility: str
    location: str | None = None
    is_archived: bool
    is_favorite: bool
    is_pinned: bool
    is_bookmarked: bool
    created_at: datetime
    updated_at: datetime
    tags: list[TagRead] = Field(default_factory=list)
    attachments: list[AttachmentRead] = Field(default_factory=list)


class DiaryShareCreate(BaseModel):
    shared_to_username: str | None = None
    expires_in_hours: int | None = None # e.g. 1, 24, 168 (7 days)


class DiaryShareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    diary_id: str
    shared_by_user_id: str
    shared_to_user_id: str | None = None
    shared_to_username: str | None = None
    expires_at: datetime | None = None
    created_at: datetime



class DiarySummary(BaseModel):
    total_entries: int
    favorites: int
    archive_count: int
    current_streak: int
    longest_streak: int
    monthly_entries: int
    mood_distribution: dict[str, int]
    recent_diaries: list[DiaryRead] = Field(default_factory=list)

