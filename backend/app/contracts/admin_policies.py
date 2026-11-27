"""Redacted administrator configuration and deterministic schedule previews."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .enums import ReviewRating, ScheduleStrategy
from .models import ContractModel, Page


class ModelProviderAdminRead(ContractModel):
    id: UUID
    user_id: UUID
    user_name: str
    name: str
    provider: str
    model_name: str
    endpoint_host: str | None
    is_enabled: bool
    is_default: bool
    version: int
    key_configured: bool
    user_billing_approved: bool
    global_billing_approved: bool
    configuration_status: Literal[
        "owner_inactive", "disabled", "configuration_invalid", "key_missing", "billing_paused", "configured"
    ]
    connection_tested: Literal[False] = False


class PolicyPatch(ContractModel):
    @model_validator(mode="after")
    def nonempty_patch(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Provide at least one setting and omit unused fields")
        return self


class ModelProviderAdminPatch(PolicyPatch):
    is_enabled: bool | None = None
    is_default: bool | None = None


Interval = Annotated[float, Field(gt=0, le=36500)]
Intervals = Annotated[list[Interval], Field(min_length=1, max_length=20)]
Retention = Annotated[float, Field(gt=0, lt=1)]


class MemoryPolicyValues(ContractModel):
    strategy: ScheduleStrategy
    intervals_days: list[float]
    target_retention: float


class MemoryPolicyAdminRead(MemoryPolicyValues):
    id: UUID
    user_id: UUID
    user_name: str
    subject_id: UUID
    subject_name: str
    version: int
    is_active: bool


class MemoryPolicyPage(Page[MemoryPolicyAdminRead]):
    defaults: MemoryPolicyValues


class MemoryPolicyPatch(PolicyPatch):
    strategy: ScheduleStrategy | None = None
    intervals_days: Intervals | None = None
    target_retention: Retention | None = None


class MemorySimulationRequest(ContractModel):
    strategy: ScheduleStrategy
    intervals_days: Intervals | None = None
    target_retention: Retention | None = None
    ratings: list[ReviewRating] = Field(
        default_factory=lambda: [ReviewRating.GOOD, ReviewRating.GOOD, ReviewRating.HARD, ReviewRating.AGAIN],
        min_length=1,
        max_length=16,
    )


class MemorySimulationStep(ContractModel):
    review_count: int
    rating: ReviewRating
    reviewed_at: datetime
    due_at: datetime
    interval_days: float | None
    stability: float | None
    difficulty: float | None
    retrievability: float | None


class MemorySimulationRead(ContractModel):
    strategy: ScheduleStrategy
    algorithm_version: str
    steps: list[MemorySimulationStep]
    simulation: Literal[True] = True
