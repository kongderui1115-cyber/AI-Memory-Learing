"""Read-only, tenant-scoped learning dashboard contract."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class ReviewWorkload(BaseModel):
    local_date: date
    timezone: str
    queued: int
    due_unqueued: int
    can_enqueue: int
    daily_limit: int
    estimated_seconds: int | None
    sample_size: int
    automatic_processing_enabled: bool


class InsightMetrics(BaseModel):
    knowledge_total: int
    chapter_total: int
    chapter_completed: int
    today_study_seconds: int
    today_review_seconds: int
    today_reviews: int
    today_tasks: int
    today_completed_tasks: int
    pending_reviews: int
    overdue_reviews: int
    learning_days: int
    streak_days: int
    recall_rate: float | None
    review_total: int


class ActivityDay(BaseModel):
    date: date
    study_seconds: int
    review_seconds: int
    reviews: int
    recalled: int


class SubjectInsight(BaseModel):
    id: UUID
    name: str
    knowledge_count: int
    chapter_count: int
    completed_chapters: int


class MemorySegment(BaseModel):
    key: str
    name: str
    count: int


class PlannedDay(BaseModel):
    date: date
    count: int
    fsrs: int
    ebbinghaus: int


class WorkspaceInsights(BaseModel):
    timezone: str
    today: date
    from_date: date
    to_date: date
    metrics: InsightMetrics
    activity: list[ActivityDay]
    subjects: list[SubjectInsight]
    memory: list[MemorySegment]
    scheduled: list[PlannedDay]
    upcoming: list[PlannedDay]
