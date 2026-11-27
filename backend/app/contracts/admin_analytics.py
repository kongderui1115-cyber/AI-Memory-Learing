"""Cross-account administrator analytics response."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class LearningDay(BaseModel):
    date: date
    knowledge: int
    study_seconds: int
    reviews: int
    assigned: int
    completed: int
    completion_rate: float | None


class SubjectActivity(BaseModel):
    id: UUID
    name: str
    knowledge: int
    assigned: int
    completed: int
    completion_rate: float | None
    reviews: int
    recall_rate: float | None
    weak: int | None


class RetentionPoint(BaseModel):
    stage: str
    subject_id: UUID | None
    subject_name: str
    observed: float | None
    predicted: float | None
    observed_samples: int
    predicted_samples: int
    prediction_versions: list[str]


class JobCounts(BaseModel):
    success: int
    failure: int
    partial: int
    average_ms: float | None
    duration_samples: int


class JobKind(JobCounts):
    key: str
    name: str


class JobDay(JobCounts):
    date: date


class JobActivity(BaseModel):
    kinds: list[JobKind]
    days: list[JobDay]


class AIUsageDay(BaseModel):
    date: date
    calls: int
    terminal_calls: int
    errors: int
    tokens: int | None
    token_samples: int


class AIBreakdown(BaseModel):
    name: str
    value: int


class AIUsage(BaseModel):
    days: list[AIUsageDay]
    models: list[AIBreakdown]
    tasks: list[AIBreakdown]


class WorkflowCounts(BaseModel):
    imported_versions: int
    generated_points: int
    sync_queued: int
    extraction_queued: int
    extraction_blocked: int
    notification_queued: int


class AdminAnalytics(BaseModel):
    as_of: datetime
    timezone: str
    from_date: date
    to_date: date
    today_due: int
    today_ai_calls: int
    learning: list[LearningDay]
    subjects: list[SubjectActivity]
    retention: list[RetentionPoint]
    jobs: JobActivity
    ai_usage: AIUsage
    workflow: WorkflowCounts
