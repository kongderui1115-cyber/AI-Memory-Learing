"""Account and chapter contracts added to the existing API v1."""

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, EmailStr, Field, HttpUrl, field_validator, model_validator
from .models import ContractModel, KnowledgePointRead, KnowledgePointWrite, Resource


class UserCreate(ContractModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=256, repr=False)
    timezone: str = "Asia/Shanghai"
    role: Literal["user", "admin"] = "user"

    @field_validator("password")
    @classmethod
    def nonblank_password(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("Password requires at least ten non-padding characters")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Unknown IANA timezone") from None
        return value


class UserAccount(Resource):
    # Existing accounts retain their stored address. Creation validates EmailStr.
    email: str
    display_name: str
    timezone: str
    role: Literal["user", "admin"]
    is_active: bool


class UserUpdate(ContractModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    role: Literal["user", "admin"] | None = None


class PasswordChange(ContractModel):
    current_password: str = Field(min_length=1, max_length=256, repr=False)
    new_password: str = Field(min_length=10, max_length=256, repr=False)

    @field_validator("new_password")
    @classmethod
    def nonblank_password(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("Password requires at least ten non-padding characters")
        return value


class SessionRead(ContractModel):
    id: UUID
    user_id: UUID
    email: str
    display_name: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    logged_out_at: datetime | None
    ip_address: str
    user_agent: str
    online: bool


class AuditRead(ContractModel):
    id: UUID
    created_at: datetime
    actor_id: UUID | None
    target_user_id: UUID | None
    actor_label: str
    action: str
    severity: str
    resource: str
    outcome: str
    ip_address: str
    request_id: UUID | None


class ChapterWrite(ContractModel):
    subject_id: UUID
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=500_000)
    status: Literal["not_started", "in_progress", "completed"] = "not_started"
    source_url: HttpUrl | None = None
    external_page_id: str | None = Field(default=None, max_length=128)


class ChapterRead(Resource):
    subject_id: UUID
    title: str
    content: str
    status: str
    source_url: str | None
    external_page_id: str | None
    completed_at: datetime | None
    notion_archived_at: datetime | None = None


class ChapterUpdate(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, max_length=500_000)
    status: Literal["not_started", "in_progress", "completed"] | None = None


class StudySessionWrite(ContractModel):
    started_at: AwareDatetime
    ended_at: AwareDatetime
    notes: str = Field(default="", max_length=10_000)

    @model_validator(mode="after")
    def valid_time(self):
        if self.ended_at < self.started_at:
            raise ValueError("End time must follow start time")
        return self


class StudySessionRead(StudySessionWrite):
    id: UUID
    chapter_id: UUID
    duration_seconds: int
    created_at: datetime


class KnowledgeWrite(KnowledgePointWrite):
    chapter_id: UUID | None = None


class KnowledgeRead(KnowledgePointRead):
    chapter_id: UUID | None = None
    source_url: str | None = None


class SubjectUpdate(ContractModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    parent_id: UUID | None = None
    description: str | None = None
    language_code: str | None = Field(default=None, max_length=16)
    tags: list[str] | None = None
    is_active: bool | None = None


class KnowledgeUpdate(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    keywords: list[str] | None = None
    tags: list[str] | None = None


class ChapterJobRead(ContractModel):
    id: UUID
    chapter_id: UUID
    content_hash: str
    status: str
    attempt: int
    error_code: str | None
    created_at: datetime


class TaskSkipRequest(ContractModel):
    reason: str | None = Field(default=None, max_length=10000)


class TaskDeferRequest(ContractModel):
    days: int = Field(ge=1, le=30)
