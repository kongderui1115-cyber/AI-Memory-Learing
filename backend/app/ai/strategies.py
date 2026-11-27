"""数据驱动的学科策略（AI-06 / FR-10）。

学科策略完全由配置数据描述：抽取提示词、题型偏好、术语表、调度参数覆盖、
通知模板覆盖。**新增学科只需注册一条配置，无需改动任何代码分支**；学科名、
术语与提示词原生支持 Unicode（中文/俄语/法语/英语等）。

契约字段严格对齐 ``SubjectStrategyWrite``；``to_contract_dict`` 只输出这 7 个
字段，额外的学科元数据（slug/name/language_code）仅用于本地索引与渲染。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .errors import ErrorDetail, StructuredOutputError
from .prompts import PROMPT_VERSION_EXTRACTION, render_template
from .validation import (
    QUESTION_TYPES,
    SUBJECT_STRATEGY_WRITE_FIELDS,
    assert_valid,
    validate_subject_strategy,
)

QUESTION_TYPE_ORDER = ("qa", "cloze", "multiple_choice", "short_explanation")

# 允许出现的学科元数据键；其余未知键按契约 extra="forbid" 明确拒绝。
ALLOWED_META_FIELDS = frozenset(
    {"subject_id", "slug", "name", "language_code", "system_prompt", "parent_id", "tags"}
)


@dataclass(frozen=True)
class SubjectStrategy:
    """一个学科的策略快照。"""

    slug: str
    name: str
    extraction_prompt: str
    prompt_version: str = PROMPT_VERSION_EXTRACTION
    question_type_preferences: tuple[str, ...] = QUESTION_TYPE_ORDER
    glossary: dict[str, str] = field(default_factory=dict)
    scheduler_overrides: dict[str, Any] = field(default_factory=dict)
    notification_template_overrides: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    subject_id: str = ""
    language_code: str = "zh-CN"
    system_prompt: str = ""
    parent_id: str | None = None
    tags: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, Any]:
        """只输出 ``SubjectStrategyWrite`` 的契约字段。"""
        return {
            "extraction_prompt": self.extraction_prompt,
            "question_type_preferences": list(self.question_type_preferences),
            "glossary": dict(self.glossary),
            "scheduler_overrides": dict(self.scheduler_overrides),
            "notification_template_overrides": dict(self.notification_template_overrides),
            "prompt_version": self.prompt_version,
            "is_active": self.is_active,
        }

    def to_config_mapping(self) -> dict[str, Any]:
        """完整可序列化配置，可用于再次注册（数据驱动持久化）。"""
        data = self.to_contract_dict()
        data.update(
            {
                "subject_id": self.subject_id,
                "slug": self.slug,
                "name": self.name,
                "language_code": self.language_code,
                "system_prompt": self.system_prompt,
                "parent_id": self.parent_id,
                "tags": list(self.tags),
            }
        )
        return data


def default_strategy() -> SubjectStrategy:
    """通用缺省策略：不含任何学科硬编码，任何新学科都能回退到此策略。"""
    return SubjectStrategy(
        slug="__default__",
        name="通用",
        extraction_prompt="",
        prompt_version=PROMPT_VERSION_EXTRACTION,
        question_type_preferences=QUESTION_TYPE_ORDER,
        glossary={},
        scheduler_overrides={},
        notification_template_overrides={},
    )


def strategy_from_mapping(data: Mapping[str, Any]) -> SubjectStrategy:
    """从配置字典解析学科策略，先做契约校验再构造。

    Raises:
        StructuredOutputError: 契约字段缺失/取值非法，或出现未知字段。
    """
    unknown = sorted(set(data) - set(SUBJECT_STRATEGY_WRITE_FIELDS) - ALLOWED_META_FIELDS)
    if unknown:
        raise StructuredOutputError(
            "学科策略含未知字段：" + ", ".join(unknown),
            details=[ErrorDetail(name, "unknown field") for name in unknown],
        )
    assert_valid(data, validate_subject_strategy, label="subject_strategy")
    prefs = tuple(data["question_type_preferences"])
    tags = data.get("tags", [])
    return SubjectStrategy(
        slug=str(data.get("slug") or data.get("name") or ""),
        name=str(data.get("name") or data.get("slug") or ""),
        extraction_prompt=data["extraction_prompt"],
        prompt_version=data["prompt_version"],
        question_type_preferences=prefs,
        glossary=dict(data["glossary"]),
        scheduler_overrides=dict(data["scheduler_overrides"]),
        notification_template_overrides=dict(data["notification_template_overrides"]),
        is_active=bool(data["is_active"]),
        subject_id=str(data.get("subject_id") or ""),
        language_code=str(data.get("language_code") or "zh-CN"),
        system_prompt=str(data.get("system_prompt") or ""),
        parent_id=data.get("parent_id"),
        tags=tuple(tags),
    )


class StrategyRegistry:
    """按 slug / subject_id 注册与解析策略；缺失回退通用缺省策略。"""

    def __init__(self, default: SubjectStrategy | None = None) -> None:
        self._by_slug: dict[str, SubjectStrategy] = {}
        self._by_id: dict[str, SubjectStrategy] = {}
        self._default = default or default_strategy()

    @property
    def default(self) -> SubjectStrategy:
        return self._default

    def register(self, strategy: SubjectStrategy) -> None:
        """注册/更新一条策略（新增学科的唯一入口，无需改代码）。"""
        if not strategy.slug:
            raise StructuredOutputError("策略必须提供 slug")
        self._by_slug[strategy.slug] = strategy
        if strategy.subject_id:
            self._by_id[strategy.subject_id] = strategy

    def get_by_slug(self, slug: str) -> SubjectStrategy | None:
        return self._by_slug.get(slug)

    def get_by_id(self, subject_id: str) -> SubjectStrategy | None:
        return self._by_id.get(subject_id)

    def resolve(
        self, *, slug: str | None = None, subject_id: str | None = None
    ) -> SubjectStrategy:
        """解析策略：命中注册项则优先活跃项，否则回退通用缺省。"""
        if subject_id and subject_id in self._by_id:
            return self._by_id[subject_id]
        if slug and slug in self._by_slug:
            return self._by_slug[slug]
        return self._default

    @property
    def slugs(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_slug))


def resolve_question_types(
    strategy: SubjectStrategy, requested: Iterable[str] | None = None
) -> list[str]:
    """确定本次出题题型：请求与学科偏好取交集，无请求则用偏好/全部题型。

    非法题型明确报错；交集为空时报错，避免静默生成不符合学科偏好的题目。
    """
    preferred = list(strategy.question_type_preferences) or list(QUESTION_TYPE_ORDER)
    if requested is None:
        return preferred
    requested_list = list(requested)
    invalid = [item for item in requested_list if item not in QUESTION_TYPES]
    if invalid:
        raise StructuredOutputError(
            "请求了非法题型：" + ", ".join(invalid),
            details=[ErrorDetail("question_type", f"invalid: {item}") for item in invalid],
        )
    if not requested_list:
        return preferred
    resolved = [item for item in requested_list if item in preferred]
    if not resolved:
        raise StructuredOutputError(
            "请求题型与学科偏好无交集，拒绝静默降级",
            details=[ErrorDetail("question_type_preferences", "no intersection")],
        )
    return resolved


def resolve_scheduler_overrides(
    strategy: SubjectStrategy, base: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """合并调度参数：学科覆盖优先于全局基线（纯逻辑，不改原对象）。"""
    merged = dict(base or {})
    merged.update(strategy.scheduler_overrides)
    return merged


def resolve_notification_overrides(
    strategy: SubjectStrategy, base: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """合并通知模板/参数覆盖：学科覆盖优先。"""
    merged = dict(base or {})
    merged.update(strategy.notification_template_overrides)
    return merged


def render_notification_override(
    strategy: SubjectStrategy,
    template_key: str,
    variables: Mapping[str, Any],
    *,
    default: str = "",
) -> str:
    """渲染学科通知模板覆盖；不存在则返回调用方提供的默认模板。"""
    override = strategy.notification_template_overrides.get(template_key, default)
    if isinstance(override, Mapping):
        override = override.get("body_template", default)
    if not isinstance(override, str) or not override:
        return default
    return render_template(override, variables, strict=False)


# ---- 内置示例学科：全部是「配置数据」，不是代码分支 -------------------------
def built_in_presets() -> dict[str, dict[str, Any]]:
    """返回 6 个示例学科配置 + 任意新学科沿用同一结构即可，无需改代码。

    含俄语、法语、英语、中文 Unicode 术语，验证全链路多语言原生支持。
    """
    base_template = (
        "你是「{subject}」学科的知识整理助手。术语表:\n{glossary}\n"
        "请把下面笔记拆解为结构化知识点，保留原文语言与术语。\n"
        "笔记标题: {note_title}\n笔记原文:\n{note_content}\n"
        "输出 JSON schema:\n{schema}"
    )
    return {
        "windows-kernel": {
            "slug": "windows-kernel",
            "name": "Windows 内核",
            "language_code": "zh-CN",
            "extraction_prompt": base_template,
            "prompt_version": "kp-extract-winkernel-v1",
            "question_type_preferences": ["qa", "short_explanation", "cloze"],
            "glossary": {"IRQL": "中断请求级别", "DPC": "延迟过程调用", "EPROCESS": "进程内核对象"},
            "scheduler_overrides": {"ebbinghaus_intervals_days": [1, 2, 4, 7, 15, 30]},
            "notification_template_overrides": {
                "review_digest": "【{subject}】{title}\n{summary}"
            },
            "is_active": True,
            "tags": ["系统", "内核"],
        },
        "english": {
            "slug": "english",
            "name": "英语",
            "language_code": "en",
            "extraction_prompt": base_template,
            "prompt_version": "kp-extract-en-v1",
            "question_type_preferences": ["cloze", "multiple_choice", "qa"],
            "glossary": {"present perfect": "现在完成时", "collocation": "词语搭配"},
            "scheduler_overrides": {"fsrs_target_retention": 0.9},
            "notification_template_overrides": {
                "review_digest": "[{subject}] {title} — {summary}"
            },
            "is_active": True,
            "tags": ["语言"],
        },
        "russian": {
            "slug": "russian",
            "name": "俄语",
            "language_code": "ru",
            "extraction_prompt": base_template,
            "prompt_version": "kp-extract-ru-v1",
            "question_type_preferences": ["cloze", "qa", "short_explanation"],
            "glossary": {"вид": "动词体", "падеж": "格", "склонение": "变格"},
            "scheduler_overrides": {"daily_limit": 20},
            "notification_template_overrides": {
                "review_digest": "【{subject}】{title}: {summary}"
            },
            "is_active": True,
            "tags": ["语言", "Unicode"],
        },
        "french": {
            "slug": "french",
            "name": "法语",
            "language_code": "fr",
            "extraction_prompt": base_template,
            "prompt_version": "kp-extract-fr-v1",
            "question_type_preferences": ["cloze", "multiple_choice"],
            "glossary": {"subjonctif": "虚拟式", "accord": "性数配合"},
            "scheduler_overrides": {"fsrs_target_retention": 0.92},
            "notification_template_overrides": {
                "review_digest": "[{subject}] {title} — {summary}"
            },
            "is_active": True,
            "tags": ["语言", "Unicode"],
        },
        "ai": {
            "slug": "ai",
            "name": "AI",
            "language_code": "zh-CN",
            "extraction_prompt": base_template,
            "prompt_version": "kp-extract-ai-v1",
            "question_type_preferences": ["qa", "short_explanation", "multiple_choice"],
            "glossary": {"transformer": "Transformer 架构", "RAG": "检索增强生成"},
            "scheduler_overrides": {"daily_limit": 25},
            "notification_template_overrides": {
                "review_digest": "【{subject}】{title}\n{summary}"
            },
            "is_active": True,
            "tags": ["技术"],
        },
        "mathematics": {
            "slug": "mathematics",
            "name": "数学",
            "language_code": "zh-CN",
            "extraction_prompt": base_template,
            "prompt_version": "kp-extract-math-v1",
            "question_type_preferences": ["qa", "short_explanation"],
            "glossary": {"∂": "偏导符号", "∑": "求和符号"},
            "scheduler_overrides": {"ebbinghaus_intervals_days": [1, 2, 4, 8, 16, 32]},
            "notification_template_overrides": {
                "review_digest": "【{subject}】{title}\n{summary}"
            },
            "is_active": True,
            "tags": ["理科"],
        },
    }


def load_registry_from_config(
    configs: Iterable[Mapping[str, Any]] = (),
    *,
    include_builtin: bool = True,
) -> StrategyRegistry:
    """从配置集合构造注册表：内置示例学科 + 任意新增学科配置。"""
    registry = StrategyRegistry()
    sources: list[Mapping[str, Any]] = []
    if include_builtin:
        sources.extend(built_in_presets().values())
    sources.extend(configs)
    for config in sources:
        registry.register(strategy_from_mapping(config))
    return registry
