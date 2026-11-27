"""Website registration and guided account configuration contracts."""

from typing import Annotated, Literal

from pydantic import EmailStr, Field, field_validator

from .core import UserCreate
from .models import ContractModel


class RegisterRequest(ContractModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=256, repr=False)

    @field_validator("display_name")
    @classmethod
    def display_name_rules(cls, value):
        if not value.strip():
            raise ValueError("请填写称呼")
        return value.strip()

    @field_validator("password")
    @classmethod
    def password_rules(cls, value):
        return UserCreate.nonblank_password(value)


class ProfileWrite(ContractModel):
    recipient_email: EmailStr
    reminder_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Shanghai"
    onboarding_step: int = Field(default=1, ge=0, le=4)

    @field_validator("timezone")
    @classmethod
    def timezone_rules(cls, value):
        return UserCreate.valid_timezone(value)


class EmailWrite(ContractModel):
    provider: str = Field(pattern=r"^(qq|163|gmail|outlook|custom)$")
    username: EmailStr
    password: str | None = Field(default=None, min_length=1, max_length=1000, repr=False)
    host: str | None = Field(default=None, max_length=253)
    port: int = Field(default=465, ge=1, le=65535)
    security: str = Field(default="ssl", pattern=r"^(ssl|starttls)$")
    enabled: bool = True


class MemoryPreferencesWrite(ContractModel):
    strategy: Literal["fsrs", "ebbinghaus"]
    intervals_days: list[Annotated[int, Field(ge=1, le=3650)]] = Field(min_length=1, max_length=30)
    learning_goal: str = Field(default="", max_length=500)
    learning_preference: str = Field(default="", max_length=500)


class NotionSecretWrite(ContractModel):
    token: str = Field(min_length=10, max_length=1000, repr=False)


class NotionConnect(ContractModel):
    external_id: str = Field(min_length=1, max_length=2048)
    source_type: str = Field(default="data_source", pattern=r"^(database|data_source|page_tree)$")
    name: str = Field(default="我的学习笔记", min_length=1, max_length=120)
    subject_name: str = Field(min_length=1, max_length=120)
    status_property: str = Field(default="状态", min_length=1, max_length=120)
    status_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "未开始": "not_started",
            "进行中": "in_progress",
            "已完成": "completed",
        }
    )


class ModelConnect(ContractModel):
    provider: str = Field(pattern=r"^(deepseek|kimi|openai|openai_compatible)$")
    model_name: str = Field(min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=1, max_length=2000, repr=False)
    base_url: str | None = None
    billing_approved: bool = False
