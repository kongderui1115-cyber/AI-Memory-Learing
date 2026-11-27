"""Shared string enums; values are persisted and exposed by REST."""

from enum import StrEnum


class ScheduleStrategy(StrEnum):
    EBBINGHAUS = "ebbinghaus"
    FSRS = "fsrs"


class ReviewRating(StrEnum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class KnowledgePointStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    MERGED = "merged"


class QuestionType(StrEnum):
    QA = "qa"
    CLOZE = "cloze"
    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_EXPLANATION = "short_explanation"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class BatchStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class NotificationChannelType(StrEnum):
    WECOM_APP = "wecom_app"
    WECHAT_OFFICIAL_ACCOUNT = "wechat_official_account"
    THIRD_PARTY_PUSH = "third_party_push"
    WECOM_WEBHOOK = "wecom_webhook"
    DINGTALK_WEBHOOK = "dingtalk_webhook"
    DINGTALK_APP = "dingtalk_app"
    SMTP = "smtp"


class NotificationJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AIProviderType(StrEnum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    OPENAI_COMPATIBLE = "openai_compatible"


class AICallStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
