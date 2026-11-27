"""AI Provider 配置读取与「就绪」硬校验（AI-01 / FR-02）。

配置全部来自环境变量；密钥按 ``credential_ref``（环境变量名）解析，
绝不写入配置对象、日志或数据库。

硬约束落点：``assert_ready`` 在 Key 缺失或 ``AI_BILLING_APPROVED != true``
时抛 ``CONFIG_MISSING``，因此调用方不可能在缺少凭据时拿到任何伪造的
理解结果。本模块为纯标准库逻辑，``env`` 可注入以便真实单元测试。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Mapping

from .errors import (
    BillingNotApprovedError,
    ConfigMissingError,
    ErrorDetail,
    StructuredOutputError,
)
from .validation import AI_PROVIDER_TYPES

# 与 app/contracts/enums.py::AIProviderType 的值严格一致
DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
}
DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

ENV_PROVIDER = "AI_PROVIDER"
ENV_MODEL = "AI_MODEL"
ENV_API_KEY = "AI_API_KEY"
ENV_API_KEY_REF = "AI_API_KEY_REF"
ENV_BASE_URL = "AI_BASE_URL"
ENV_TIMEOUT = "AI_TIMEOUT_SECONDS"
ENV_MAX_RETRIES = "AI_MAX_RETRIES"
ENV_RATE_LIMIT = "AI_RATE_LIMIT_PER_MINUTE"
ENV_TEMPERATURE = "AI_TEMPERATURE"
ENV_ENABLED = "AI_ENABLED"
ENV_IS_DEFAULT = "AI_IS_DEFAULT"
ENV_BILLING_APPROVED = "AI_BILLING_APPROVED"


@dataclass(frozen=True)
class AIProviderConfig:
    """对齐契约 ``AIProviderConfigWrite``，另附运行参数。

    ``credential_ref`` 是环境变量名而非密钥值（契约 §3）；``provider``、
    ``temperature``、``timeout_seconds``、``max_retries``、
    ``rate_limit_per_minute`` 均可配置，切换供应商不改业务代码。
    """

    name: str
    provider: str
    model_name: str
    credential_ref: str = ENV_API_KEY
    base_url: str | None = None
    temperature: float = 0.2
    timeout_seconds: int = 60
    max_retries: int = 3
    rate_limit_per_minute: int | None = None
    is_enabled: bool = True
    is_default: bool = False
    config_id: str = ""  # 持久层 UUID（AIProviderConfigRead.id），非 Write 契约字段

    def resolved_base_url(self) -> str:
        """返回最终 base_url；openai_compatible 未配置则明确报错。"""
        if self.base_url:
            return self.base_url.rstrip("/")
        default = DEFAULT_BASE_URLS.get(self.provider)
        if not default:
            raise ConfigMissingError(
                "provider=openai_compatible 必须通过 AI_BASE_URL 配置兼容端点",
                details=[ErrorDetail("AI_BASE_URL", "required for openai_compatible")],
            )
        return default

    def validate(self) -> None:
        """按契约范围校验配置，非法值明确报错而非静默兜底。"""
        errors: list[str] = []
        if self.provider not in AI_PROVIDER_TYPES:
            errors.append(f"provider 非法: {self.provider!r}，应为 {sorted(AI_PROVIDER_TYPES)}")
        if not self.name.strip():
            errors.append("name 不能为空")
        if not self.model_name.strip():
            errors.append("model_name 不能为空（AI_MODEL 未配置）")
        if not self.credential_ref.strip():
            errors.append("credential_ref 不能为空")
        if not (0.0 <= self.temperature <= 2.0):
            errors.append("temperature 必须处于 0..2")
        if self.timeout_seconds <= 0:
            errors.append("timeout_seconds 必须 > 0")
        if self.max_retries < 0:
            errors.append("max_retries 必须 >= 0")
        if self.rate_limit_per_minute is not None and self.rate_limit_per_minute <= 0:
            errors.append("rate_limit_per_minute 必须 > 0")
        if errors:
            raise StructuredOutputError(
                "AI Provider 配置非法：" + "；".join(errors),
                details=[ErrorDetail("config", reason) for reason in errors],
            )

    def retry_policy_kwargs(self) -> dict[str, int]:
        return {"max_retries": self.max_retries}


def _parse_int(
    env: Mapping[str, str], key: str, default: int, *, minimum: int | None = None
) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise StructuredOutputError(
            f"环境变量 {key} 必须是整数，实际为 {raw!r}",
            details=[ErrorDetail(key, "not an integer")],
        ) from exc
    if minimum is not None and value < minimum:
        raise StructuredOutputError(
            f"环境变量 {key} 必须 >= {minimum}，实际为 {value}",
            details=[ErrorDetail(key, "out of range")],
        )
    return value


def _parse_optional_int(env: Mapping[str, str], key: str) -> int | None:
    raw = (env.get(key) or "").strip()
    if not raw:
        return None
    return _parse_int(env, key, 0, minimum=1)


def _parse_float(
    env: Mapping[str, str], key: str, default: float, low: float, high: float
) -> float:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise StructuredOutputError(
            f"环境变量 {key} 必须是浮点数，实际为 {raw!r}",
            details=[ErrorDetail(key, "not a float")],
        ) from exc
    if not (low <= value <= high):
        raise StructuredOutputError(
            f"环境变量 {key} 必须处于 {low}..{high}，实际为 {value}",
            details=[ErrorDetail(key, "out of range")],
        )
    return value


def _parse_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = (env.get(key) or "").strip().lower()
    if not raw:
        return default
    if raw not in ("true", "false", "1", "0"):
        raise StructuredOutputError(
            f"环境变量 {key} 必须是 true/false，实际为 {raw!r}",
            details=[ErrorDetail(key, "not a boolean")],
        )
    return raw in ("true", "1")


def load_provider_config(
    env: Mapping[str, str] | None = None, *, name: str = "default"
) -> AIProviderConfig:
    """从环境变量构造配置（不联网、不读密钥文件、不接触数据库）。"""
    e: Mapping[str, str] = os.environ if env is None else env
    provider = (e.get(ENV_PROVIDER) or "").strip().lower() or "deepseek"
    model = (e.get(ENV_MODEL) or "").strip() or DEFAULT_MODELS.get(provider, "")
    base_url = (e.get(ENV_BASE_URL) or "").strip() or DEFAULT_BASE_URLS.get(provider)
    credential_ref = (e.get(ENV_API_KEY_REF) or "").strip() or ENV_API_KEY
    return AIProviderConfig(
        name=name,
        provider=provider,
        model_name=model,
        credential_ref=credential_ref,
        base_url=base_url,
        temperature=_parse_float(e, ENV_TEMPERATURE, 0.2, 0.0, 2.0),
        timeout_seconds=_parse_int(e, ENV_TIMEOUT, 60, minimum=1),
        max_retries=_parse_int(e, ENV_MAX_RETRIES, 3, minimum=0),
        rate_limit_per_minute=_parse_optional_int(e, ENV_RATE_LIMIT),
        is_enabled=_parse_bool(e, ENV_ENABLED, True),
        is_default=_parse_bool(e, ENV_IS_DEFAULT, False),
    )


def billing_approved(env: Mapping[str, str] | None = None) -> bool:
    """仅当 ``AI_BILLING_APPROVED`` 严格等于 true（忽略大小写）时为 True。"""
    e: Mapping[str, str] = os.environ if env is None else env
    return (e.get(ENV_BILLING_APPROVED) or "").strip().lower() == "true"


def collect_readiness_problems(
    config: AIProviderConfig, env: Mapping[str, str] | None = None
) -> list[tuple[str, str]]:
    """纯逻辑：收集阻止真实调用的全部原因，返回 ``(field, reason)`` 列表。"""
    e: Mapping[str, str] = os.environ if env is None else env
    problems: list[tuple[str, str]] = []
    if not config.is_enabled:
        problems.append(("is_enabled", "该 Provider 配置为禁用"))
    key = (e.get(config.credential_ref) or "").strip()
    if not key:
        problems.append((config.credential_ref, "API Key 环境变量未配置或为空"))
    if not billing_approved(e):
        problems.append((ENV_BILLING_APPROVED, "用户未授权计费调用，必须显式设为 true"))
    return problems


def ensure_billing_approved(env: Mapping[str, str] | None = None) -> None:
    """单独校验计费授权，未通过抛 ``BillingNotApprovedError``。"""
    if not billing_approved(env):
        raise BillingNotApprovedError(
            "用户未授权计费调用：AI_BILLING_APPROVED != true，已阻止真实 API 调用，"
            "不得返回伪造的理解结果。",
            details=[ErrorDetail(ENV_BILLING_APPROVED, "must be 'true'")],
        )


def assert_ready(
    config: AIProviderConfig, env: Mapping[str, str] | None = None
) -> str:
    """硬约束入口：校验通过后返回真实 API Key，否则抛明确错误。

    未配置 Key 或计费未授权时**绝不**返回任何伪造结果；错误体携带
    ``CONFIG_MISSING`` 与逐条 ``details``，便于 API 层直接映射为 5xx。
    """
    e: Mapping[str, str] = os.environ if env is None else env
    config.validate()
    problems = collect_readiness_problems(config, e)
    if problems:
        details = [ErrorDetail(field, reason) for field, reason in problems]
        summary = "；".join(f"{field}: {reason}" for field, reason in problems)
        if len(problems) == 1 and problems[0][0] == ENV_BILLING_APPROVED:
            raise BillingNotApprovedError(
                "AI Provider 未就绪，已阻止真实调用（禁止伪造理解结果）：" + summary,
                details=details,
            )
        raise ConfigMissingError(
            "AI Provider 未就绪，已阻止真实调用（禁止伪造理解结果）：" + summary,
            details=details,
        )
    return (e.get(config.credential_ref) or "").strip()


def with_model(config: AIProviderConfig, model_name: str) -> AIProviderConfig:
    """返回一个仅替换模型名的配置副本（切换模型不改业务代码）。"""
    return replace(config, model_name=model_name)
