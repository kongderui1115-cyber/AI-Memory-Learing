"""Pydantic v2 request/response models for API v1; no business logic."""

from datetime import date, datetime, timezone
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_serializer,
)

from .enums import (
    AICallStatus,
    AIProviderType,
    BatchStatus,
    KnowledgePointStatus,
    NotificationChannelType,
    NotificationJobStatus,
    QuestionType,
    ReviewRating,
    RunStatus,
    ScheduleStrategy,
    TaskStatus,
)

T = TypeVar("T")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    @field_serializer("*", mode="wrap", when_used="json")
    def utc_json(self, value, handler):
        if isinstance(value, datetime) and value.utcoffset() is not None:
            value = value.astimezone(timezone.utc)
        return handler(value)


class ErrorDetail(ContractModel):
    field: str | None = None
    reason: str


class ErrorBody(ContractModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: UUID
    retryable: bool = False


class ErrorResponse(ContractModel):
    error: ErrorBody


class Page(ContractModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool


class Resource(ContractModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1)


class TokenRequest(ContractModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class TokenResponse(ContractModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int = Field(gt=0)


class UserRead(Resource):
    email: EmailStr
    display_name: str
    timezone: str
    is_active: bool


class SubjectWrite(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    parent_id: UUID | None = None
    description: str | None = None
    language_code: str = Field(default="zh-CN", max_length=16)
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class SubjectRead(Resource, SubjectWrite):
    pass


class SubjectStrategyWrite(ContractModel):
    extraction_prompt: str = Field(min_length=1)
    question_type_preferences: list[QuestionType] = Field(default_factory=list)
    glossary: dict[str, str] = Field(default_factory=dict)
    scheduler_overrides: dict[str, Any] = Field(default_factory=dict)
    notification_template_overrides: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str = Field(min_length=1, max_length=40)
    is_active: bool = True


class SubjectStrategyRead(Resource, SubjectStrategyWrite):
    subject_id: UUID


class NotionIntegrationWrite(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    credential_ref: str = Field(min_length=1, max_length=160)
    api_version: str = "2022-06-28"
    is_enabled: bool = True


class NotionIntegrationRead(Resource, NotionIntegrationWrite):
    last_validated_at: datetime | None = None


class NotionDataSourceWrite(ContractModel):
    integration_id: UUID
    source_type: Literal["database", "page_tree"]
    external_source_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    sync_interval_minutes: int = Field(default=60, ge=5)
    is_enabled: bool = True


class NotionDataSourceRead(Resource, NotionDataSourceWrite):
    last_edited_watermark: datetime | None = None
    next_sync_at: datetime | None = None


class SyncRunRead(ContractModel):
    id: UUID
    data_source_id: UUID
    trigger_type: Literal["manual", "scheduled"]
    status: RunStatus
    watermark_from: datetime | None = None
    watermark_to: datetime | None = None
    items_seen: int = 0
    items_imported: int = 0
    items_failed: int = 0
    attempt: int = 1
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class RawNoteRead(ContractModel):
    id: UUID
    data_source_id: UUID
    external_page_id: str
    external_version: str
    last_edited_time: datetime
    title: str
    content_markdown: str
    content_hash: str
    source_url: HttpUrl
    metadata: dict[str, Any] = Field(default_factory=dict)
    synced_at: datetime


class KnowledgePointWrite(ContractModel):
    subject_id: UUID
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    summary: str
    difficulty: int = Field(ge=1, le=5)
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: KnowledgePointStatus = KnowledgePointStatus.DRAFT


class KnowledgePointRead(Resource, KnowledgePointWrite):
    manual_revision: bool
    merged_into_id: UUID | None = None
    canonical_hash: str


class KnowledgeMergeRequest(ContractModel):
    target_id: UUID
    reason: str | None = None


class ReviewItemWrite(ContractModel):
    question_type: QuestionType
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    explanation: str = ""
    summary: str = ""
    options: list[str] | None = None


class ReviewItemRead(Resource, ReviewItemWrite):
    knowledge_point_id: UUID
    item_version: int = Field(ge=1)
    is_current: bool
    manual_revision: bool
    provider_config_id: UUID | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    ai_call_log_id: UUID | None = None


class ScheduleStateRead(Resource):
    knowledge_point_id: UUID
    strategy: ScheduleStrategy
    due_at: datetime
    last_reviewed_at: datetime | None = None
    review_count: int = Field(ge=0)
    lapse_count: int = Field(ge=0)
    interval_index: int = Field(ge=0)
    interval_days: float | None = None
    stability: float | None = None
    difficulty: float | None = None
    retrievability: float | None = None
    target_retention: float | None = None
    algorithm_version: str
    parameters: dict[str, Any]
    last_calculation: dict[str, Any]
    strategy_changed_at: datetime


class ScheduleSwitchRequest(ContractModel):
    strategy: ScheduleStrategy
    parameters: dict[str, Any] = Field(default_factory=dict)


class ScheduleProjection(ContractModel):
    due_at: datetime
    state: dict[str, Any]
    explanation: dict[str, Any]


class ScheduleCompareResponse(ContractModel):
    ebbinghaus: ScheduleProjection
    fsrs: ScheduleProjection


class DailyGenerateRequest(ContractModel):
    local_date: date
    timezone: str = Field(min_length=1, max_length=64)
    daily_limit: int = Field(default=30, ge=1, le=500)
    subject_id: UUID | None = None


class DailyTaskRead(Resource):
    knowledge_title: str = ""
    subject_id: UUID | None = None
    skip_reason: str | None = None
    batch_id: UUID
    knowledge_point_id: UUID
    review_item_id: UUID | None = None
    scheduled_due_at: datetime
    priority: int
    position: int
    status: TaskStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DailyBatchRead(Resource):
    local_date: date
    timezone: str
    subject_id: UUID | None = None
    daily_limit: int
    status: BatchStatus
    generated_at: datetime
    tasks: list[DailyTaskRead] = Field(default_factory=list)


class ReviewCompleteRequest(ContractModel):
    rating: ReviewRating
    duration_seconds: int = Field(ge=0)
    answer_self_assessment: str | None = None
    notes: str | None = None
    reviewed_at: AwareDatetime


class ReviewHistoryRead(ContractModel):
    knowledge_title: str = ""
    subject_id: UUID | None = None
    id: UUID
    task_id: UUID
    knowledge_point_id: UUID
    review_item_id: UUID | None = None
    strategy: ScheduleStrategy
    rating: ReviewRating
    duration_seconds: int
    answer_self_assessment: str | None = None
    notes: str | None = None
    reviewed_at: datetime
    previous_schedule: dict[str, Any]
    result_schedule: dict[str, Any]


class ReviewCompleteResponse(ContractModel):
    task: DailyTaskRead
    history: ReviewHistoryRead
    schedule: ScheduleStateRead


class TrendPoint(ContractModel):
    date: date
    value: float


class HeatmapPoint(ContractModel):
    date: date
    count: int = Field(ge=0)


class StatisticsRead(ContractModel):
    from_date: date
    to_date: date
    total_tasks: int
    completed_tasks: int
    completion_rate: float = Field(ge=0, le=1)
    retention_trend: list[TrendPoint]
    heatmap: list[HeatmapPoint]


class ChannelConfigWrite(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    channel_type: NotificationChannelType
    credential_ref: str = Field(min_length=1, max_length=160)
    settings: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    is_default: bool = False


class ChannelConfigRead(Resource, ChannelConfigWrite):
    pass


class TemplateWrite(ContractModel):
    subject_id: UUID | None = None
    channel_type: NotificationChannelType
    template_key: str = Field(min_length=1, max_length=80)
    title_template: str
    body_template: str = Field(min_length=1)
    schema_variables: list[str] = Field(default_factory=list)
    max_length: int | None = Field(default=None, gt=0)
    is_active: bool = True


class TemplateRead(Resource, TemplateWrite):
    pass


class NotificationJobRead(Resource):
    task_id: UUID
    channel_config_id: UUID
    template_id: UUID
    status: NotificationJobStatus
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    sent_at: datetime | None = None


class NotificationDeliveryRead(ContractModel):
    id: UUID
    job_id: UUID
    attempt_no: int
    status: Literal["sending", "sent", "failed"]
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    attempted_at: datetime


class AIProviderConfigWrite(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    provider: AIProviderType
    model_name: str = Field(min_length=1)
    base_url: HttpUrl | None = None
    credential_ref: str = Field(min_length=1, max_length=160)
    temperature: float = Field(default=0.2, ge=0, le=2)
    timeout_seconds: int = Field(default=60, gt=0)
    max_retries: int = Field(default=3, ge=0)
    rate_limit_per_minute: int | None = Field(default=None, gt=0)
    is_enabled: bool = True
    is_default: bool = False


class AIProviderConfigRead(Resource, AIProviderConfigWrite):
    pass


class AICallLogRead(ContractModel):
    id: UUID
    provider_config_id: UUID
    operation: str
    provider: AIProviderType
    model_name: str
    prompt_version: str
    request_id: UUID
    status: AICallStatus
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None
    attempt_count: int
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class AsyncOperationRead(ContractModel):
    operation_id: UUID
    status: RunStatus


class ProviderValidation(ContractModel):
    valid: bool
    provider: AIProviderType
    model: str


class ChannelValidation(ContractModel):
    valid: bool
    channel_type: NotificationChannelType
