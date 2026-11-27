"""契约对齐常量与结构化输出校验（纯标准库）。

本模块**不 import** ``app.contracts``（其依赖 pydantic，当前环境未安装），
而是以常量复刻冻结契约的枚举值与字段名；单测通过 ``ast`` 解析
``backend/app/contracts/enums.py`` / ``models.py`` 做零偏差比对。
所有校验返回错误列表，由 ``assert_valid`` 统一抛显式异常。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Iterable, Mapping

from .errors import ErrorDetail, StructuredOutputError

# ---- 枚举值：与 app/contracts/enums.py 严格一致 -----------------------------
AI_PROVIDER_TYPES = frozenset({"openai", "deepseek", "openai_compatible"})
AI_CALL_STATUSES = frozenset({"pending", "running", "succeeded", "failed", "cancelled"})
QUESTION_TYPES = frozenset({"qa", "cloze", "multiple_choice", "short_explanation"})
KNOWLEDGE_POINT_STATUSES = frozenset({"draft", "active", "archived", "merged"})
RUN_STATUSES = frozenset({"pending", "running", "succeeded", "failed", "partial", "cancelled"})
TRIGGER_TYPES = frozenset({"manual", "scheduled"})
SOURCE_TYPES = frozenset({"database", "page_tree"})

# ---- 契约字段名：与 app/contracts/models.py 严格一致（顺序无关） ------------
AICALL_LOG_READ_FIELDS = (
    "id", "provider_config_id", "operation", "provider", "model_name",
    "prompt_version", "request_id", "status", "input_tokens", "output_tokens",
    "total_tokens", "duration_ms", "attempt_count", "error_code",
    "error_message", "started_at", "finished_at",
)
KNOWLEDGE_POINT_WRITE_FIELDS = (
    "subject_id", "title", "body", "summary", "difficulty", "keywords", "tags", "status",
)
REVIEW_ITEM_WRITE_FIELDS = (
    "question_type", "question", "answer", "explanation", "summary", "options",
)
REVIEW_ITEM_READ_EXTRA_FIELDS = (
    "knowledge_point_id", "item_version", "is_current", "manual_revision",
    "provider_config_id", "model_name", "prompt_version", "ai_call_log_id",
)
SUBJECT_STRATEGY_WRITE_FIELDS = (
    "extraction_prompt", "question_type_preferences", "glossary",
    "scheduler_overrides", "notification_template_overrides", "prompt_version", "is_active",
)
AI_PROVIDER_CONFIG_WRITE_FIELDS = (
    "name", "provider", "model_name", "base_url", "credential_ref", "temperature",
    "timeout_seconds", "max_retries", "rate_limit_per_minute", "is_enabled", "is_default",
)
SYNC_RUN_READ_FIELDS = (
    "id", "data_source_id", "trigger_type", "status", "watermark_from", "watermark_to",
    "items_seen", "items_imported", "items_failed", "attempt", "started_at",
    "finished_at", "error_code", "error_message",
)
RAW_NOTE_READ_FIELDS = (
    "id", "data_source_id", "external_page_id", "external_version",
    "last_edited_time", "title", "content_markdown", "content_hash", "source_url",
    "metadata", "synced_at",
)

_WHITESPACE = re.compile(r"\s+")


def canonical_hash(title: str, body: str) -> str:
    """知识点的规范化内容哈希（sha256 hex，64 位）。

    对齐 ``knowledge_points.canonical_hash char(64)``；仅折叠空白与去首尾，
    保留 Unicode 原文（俄语/法语/中文/英语），不做大小写折叠以免误合并。
    """
    normalized = _WHITESPACE.sub(" ", f"{title.strip()}\n{body.strip()}".strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_hash(*parts: str) -> str:
    """原文内容哈希（sha256 hex），对齐 ``raw_notes.content_hash char(64)``。"""
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _require_fields(
    data: Mapping[str, Any], fields: Iterable[str], errors: list[str]
) -> None:
    missing = [name for name in fields if name not in data]
    if missing:
        errors.append(f"缺少契约字段: {missing}")


def _require_nonempty_str(
    data: Mapping[str, Any], name: str, errors: list[str], *, max_length: int | None = None
) -> None:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{name} 必须为非空字符串")
    elif max_length is not None and len(value) > max_length:
        errors.append(f"{name} 长度超过 {max_length}")


def _require_str_list(
    data: Mapping[str, Any], name: str, errors: list[str], *, required: bool = True
) -> None:
    if name not in data and not required:
        return
    value = data.get(name)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{name} 必须为 list[str]")


def validate_knowledge_point(data: Mapping[str, Any]) -> list[str]:
    """校验结构化知识点输出是否对齐 ``KnowledgePointWrite``。"""
    errors: list[str] = []
    _require_fields(data, KNOWLEDGE_POINT_WRITE_FIELDS, errors)
    _require_nonempty_str(data, "title", errors, max_length=300)
    _require_nonempty_str(data, "body", errors)
    if "summary" in data and not isinstance(data["summary"], str):
        errors.append("summary 必须为字符串")
    difficulty = data.get("difficulty")
    if not isinstance(difficulty, int) or isinstance(difficulty, bool) or not (1 <= difficulty <= 5):
        errors.append("difficulty 必须为 1..5 的整数")
    _require_str_list(data, "keywords", errors)
    _require_str_list(data, "tags", errors)
    status = data.get("status")
    if status not in KNOWLEDGE_POINT_STATUSES:
        errors.append(f"status 非法: {status!r}，应为 {sorted(KNOWLEDGE_POINT_STATUSES)}")
    if "subject_id" in data and not isinstance(data["subject_id"], str):
        errors.append("subject_id 必须为 UUID 字符串")
    return errors


CLOZE_PLACEHOLDER = re.compile(r"_{2,}|\{\{.+?\}\}")


def validate_review_item(data: Mapping[str, Any]) -> list[str]:
    """校验多题型题目输出是否对齐 ``ReviewItemWrite``。

    - ``multiple_choice`` 必须提供 >= 2 个字符串选项；
    - ``cloze`` 题面必须含空格占位（``____`` 或 ``{{...}}``）；
    - 其余题型不要求 options。
    """
    errors: list[str] = []
    _require_fields(data, REVIEW_ITEM_WRITE_FIELDS, errors)
    question_type = data.get("question_type")
    if question_type not in QUESTION_TYPES:
        errors.append(f"question_type 非法: {question_type!r}，应为 {sorted(QUESTION_TYPES)}")
    _require_nonempty_str(data, "question", errors)
    _require_nonempty_str(data, "answer", errors)
    for optional_text in ("explanation", "summary"):
        if optional_text in data and not isinstance(data[optional_text], str):
            errors.append(f"{optional_text} 必须为字符串")
    options = data.get("options")
    if question_type == "multiple_choice":
        if not isinstance(options, list) or len(options) < 2 or any(
            not isinstance(item, str) or not item.strip() for item in options
        ):
            errors.append("multiple_choice 必须提供至少 2 个非空字符串 options")
    elif options is not None and not isinstance(options, list):
        errors.append("options 必须为 list[str] 或 null")
    if question_type == "cloze" and isinstance(data.get("question"), str):
        if not CLOZE_PLACEHOLDER.search(data["question"]):
            errors.append("cloze 题面必须含空格占位（____ 或 {{...}}）")
    return errors


def validate_subject_strategy(data: Mapping[str, Any]) -> list[str]:
    """校验学科策略配置是否对齐 ``SubjectStrategyWrite``。"""
    errors: list[str] = []
    _require_fields(data, SUBJECT_STRATEGY_WRITE_FIELDS, errors)
    _require_nonempty_str(data, "extraction_prompt", errors)
    _require_nonempty_str(data, "prompt_version", errors, max_length=40)
    prefs = data.get("question_type_preferences")
    if not isinstance(prefs, list) or any(item not in QUESTION_TYPES for item in prefs):
        errors.append(f"question_type_preferences 必须为合法 QuestionType 列表: {sorted(QUESTION_TYPES)}")
    glossary = data.get("glossary")
    if not isinstance(glossary, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in (glossary or {}).items()
    ):
        errors.append("glossary 必须为 dict[str, str]")
    for name in ("scheduler_overrides", "notification_template_overrides"):
        if name in data and not isinstance(data[name], dict):
            errors.append(f"{name} 必须为对象")
    if "is_active" in data and not isinstance(data["is_active"], bool):
        errors.append("is_active 必须为布尔值")
    return errors


def validate_ai_provider_config(data: Mapping[str, Any]) -> list[str]:
    """校验 Provider 配置是否对齐 ``AIProviderConfigWrite`` 的取值范围。"""
    errors: list[str] = []
    _require_fields(data, AI_PROVIDER_CONFIG_WRITE_FIELDS, errors)
    if data.get("provider") not in AI_PROVIDER_TYPES:
        errors.append("provider 非法")
    _require_nonempty_str(data, "name", errors, max_length=120)
    _require_nonempty_str(data, "model_name", errors)
    _require_nonempty_str(data, "credential_ref", errors, max_length=160)
    temperature = data.get("temperature")
    if not isinstance(temperature, (int, float)) or not (0 <= temperature <= 2):
        errors.append("temperature 必须处于 0..2")
    timeout = data.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout <= 0:
        errors.append("timeout_seconds 必须 > 0")
    retries = data.get("max_retries")
    if not isinstance(retries, int) or retries < 0:
        errors.append("max_retries 必须 >= 0")
    rate = data.get("rate_limit_per_minute")
    if rate is not None and (not isinstance(rate, int) or rate <= 0):
        errors.append("rate_limit_per_minute 必须为 > 0 的整数或 null")
    return errors


def assert_valid(
    data: Mapping[str, Any],
    validator: Callable[[Mapping[str, Any]], list[str]],
    *,
    label: str,
) -> None:
    """校验失败抛 ``StructuredOutputError``（携带逐条 details）。"""
    errors = validator(data)
    if errors:
        raise StructuredOutputError(
            f"{label} 未通过契约校验：" + "；".join(errors),
            details=[ErrorDetail(label, reason) for reason in errors],
        )
