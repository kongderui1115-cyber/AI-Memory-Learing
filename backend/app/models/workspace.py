"""User onboarding preferences and write-only encrypted integration credentials."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UserFkMixin, UUIDPkMixin, VersionMixin


class WorkspaceProfile(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "workspace_profiles"
    onboarding_step: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recipient_email: Mapped[str | None] = mapped_column(String(254))
    reminder_time: Mapped[str] = mapped_column(
        String(5), nullable=False, server_default=text("'09:00'")
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    ai_billing_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    email_settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    review_preferences: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_workspace_profile_user"),
        CheckConstraint("onboarding_step BETWEEN 0 AND 4", name="onboarding_step_range"),
    )


class UserSecret(UUIDPkMixin, UserFkMixin, TimestampMixin, Base):
    __tablename__ = "user_secrets"
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_secret_name"),)
