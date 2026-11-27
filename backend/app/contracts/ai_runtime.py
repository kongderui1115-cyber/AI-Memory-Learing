"""Bounded model configuration and persistent chapter-job responses."""

from pydantic import Field

from .models import AIProviderConfigWrite, ContractModel


class ProviderWrite(AIProviderConfigWrite):
    model_name: str = Field(min_length=1, max_length=120)
    credential_ref: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,159}$")
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=5)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=1000)


class ProviderUpdate(ContractModel):
    name: str | None = None
    provider: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    credential_ref: str | None = None
    temperature: float | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None
    rate_limit_per_minute: int | None = None
    is_enabled: bool | None = None
    is_default: bool | None = None
