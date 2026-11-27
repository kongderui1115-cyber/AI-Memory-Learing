"""Owner-scoped projection of the durable Notion and extraction queues."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SyncProgress(BaseModel):
    id: UUID
    source_id: UUID
    status: str
    imported: int
    attempt: int
    finished_at: datetime | None
    next_retry_at: datetime | None
    error_code: str | None


class EvidencePoint(BaseModel):
    knowledge_point_id: UUID
    source_quote: str
    source_start: int
    source_end: int
    concepts: list[str]
    terms: list[str]
    relationships: list[str]
    prerequisites: list[str]
    pitfalls: list[str]
    key_points: list[str]
    applications: list[str]
    review_suggestion: str


class ProcessingNote(BaseModel):
    chapter_id: UUID
    title: str
    source_url: str | None
    notion_archived_at: datetime | None
    learning_status: str
    job_id: UUID | None = None
    status: str | None = None
    error_code: str | None = None
    next_attempt_at: datetime | None = None
    note_summary: str | None = None
    information_sufficient: bool | None = None
    limitations: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[UUID] = Field(default_factory=list)
    evidence: list[EvidencePoint] = Field(default_factory=list)


class ProcessingProgress(BaseModel):
    automatic_processing_enabled: bool
    sync_runs: list[SyncProgress]
    notes: list[ProcessingNote]
