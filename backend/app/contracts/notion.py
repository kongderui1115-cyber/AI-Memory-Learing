"""Runtime source configuration. Secrets remain in owner-scoped environment variables."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from .models import ContractModel, Resource


class IntegrationWrite(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    credential_ref: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,159}$")
    api_version: Literal["2022-06-28", "2025-09-03", "2026-03-11"] = "2026-03-11"
    is_enabled: bool = True


class IntegrationRead(Resource, IntegrationWrite):
    last_validated_at: datetime | None = None


class IntegrationUpdate(ContractModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    credential_ref: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,159}$")
    api_version: Literal["2022-06-28", "2025-09-03", "2026-03-11"] | None = None
    is_enabled: bool | None = None


class SourceWrite(ContractModel):
    integration_id: UUID
    subject_id: UUID
    source_type: Literal["database", "data_source", "page_tree"] = "data_source"
    external_source_id: UUID
    name: str = Field(min_length=1, max_length=120)
    sync_interval_minutes: int = Field(default=60, ge=5, le=10080)
    is_enabled: bool = True
    status_property: str = Field(default="状态", min_length=1, max_length=120)
    status_mapping: dict[str, Literal["not_started", "in_progress", "completed"]] = Field(
        default_factory=lambda: {
            "未开始": "not_started",
            "进行中": "in_progress",
            "已完成": "completed",
        }
    )

    @field_validator("status_mapping")
    @classmethod
    def validate_mapping(cls, value):
        if not value or len(value) > 50 or any(not name or len(name) > 120 for name in value):
            raise ValueError("Status mapping requires 1 to 50 nonempty option names")
        return value


class SourceRead(Resource):
    integration_id: UUID
    subject_id: UUID | None
    source_type: str
    external_source_id: str
    name: str
    sync_interval_minutes: int
    is_enabled: bool
    status_property: str
    status_mapping: dict
    last_edited_watermark: datetime | None
    next_sync_at: datetime | None


class SourceUpdate(ContractModel):
    subject_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sync_interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    is_enabled: bool | None = None
    status_property: str | None = Field(default=None, min_length=1, max_length=120)
    status_mapping: dict[str, Literal["not_started", "in_progress", "completed"]] | None = None


class RawNoteView(ContractModel):
    id: UUID
    data_source_id: UUID
    sync_run_id: UUID
    external_page_id: str
    external_version: str
    last_edited_time: datetime
    title: str | None
    content_markdown: str | None
    content_hash: str
    source_url: str | None
    note_metadata: dict
    synced_at: datetime
