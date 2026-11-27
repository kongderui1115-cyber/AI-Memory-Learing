"""ORM 模型汇总（BE-02）。

导入全部模型模块以填充 ``Base.metadata``；``target_metadata`` 供 Alembic 使用。
字段 / 约束 / 索引严格对应 DATABASE_SCHEMA.md，PostgreSQL 为唯一目标库。
"""
from .base import Base
from .identity import Subject, SubjectStrategy, User
from .notion import NotionDataSource, NotionIntegration, RawNote, SyncRun
from .knowledge import KnowledgePoint, KnowledgePointSource, ReviewItem
from .scheduling import DailyReviewBatch, DailyReviewTask, ReviewHistory, ScheduleState
from .notification import (
    NotificationChannelConfig, NotificationDelivery, NotificationJob, NotificationTemplate,
)
from .ai import AICallLog, AIProviderConfig

from .runtime import UserSession, LoginThrottle, AuditEvent, IdempotencyRecord, Chapter, StudySession, ChapterJob
from .workspace import WorkspaceProfile, UserSecret
from .ownership import install_owner_constraints

install_owner_constraints(Base.metadata)
target_metadata = Base.metadata

__all__ = [
    "WorkspaceProfile", "UserSecret", "Base", "target_metadata", "UserSession", "LoginThrottle", "AuditEvent", "IdempotencyRecord", "Chapter", "StudySession", "ChapterJob",
    "User", "Subject", "SubjectStrategy",
    "NotionIntegration", "NotionDataSource", "SyncRun", "RawNote",
    "KnowledgePoint", "KnowledgePointSource", "ReviewItem",
    "ScheduleState", "DailyReviewBatch", "DailyReviewTask", "ReviewHistory",
    "NotificationChannelConfig", "NotificationTemplate", "NotificationJob", "NotificationDelivery",
    "AIProviderConfig", "AICallLog",
]
