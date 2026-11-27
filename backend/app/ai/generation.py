"""自动生成复习问题 / 答案 / 解析 / 摘要（AI-04 / FR-04）。

支持多题型（qa / cloze / multiple_choice / short_explanation）、版本化、
重新生成与人工编辑保护，并完整保留生成来源元数据
（provider_config_id / model_name / prompt_version / ai_call_log_id）。

核心的请求构造、结构化输出解析与校验、版本分配均为纯标准库逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, TYPE_CHECKING

from .config import AIProviderConfig
from .errors import ErrorDetail, StructuredOutputError
from .extraction import _as_mapping
from .ports import GenerationMeta, StructuredRequest
from .prompts import (
    GENERATION_SCHEMA_HINT,
    PROMPT_VERSION_GENERATION,
    build_generation_prompt,
)
from .strategies import SubjectStrategy, resolve_question_types
from .validation import (
    REVIEW_ITEM_READ_EXTRA_FIELDS,
    REVIEW_ITEM_WRITE_FIELDS,
    assert_valid,
    validate_review_item,
)

if TYPE_CHECKING:
    from .service import AIExecutionService


@dataclass(frozen=True)
class ReviewItemDraft:
    """对齐 ``ReviewItemWrite`` + ``ReviewItemRead`` 附加字段。"""

    knowledge_point_id: str
    question_type: str
    question: str
    answer: str
    explanation: str = ""
    summary: str = ""
    options: list[str] | None = None
    item_version: int = 1
    is_current: bool = True
    manual_revision: bool = False
    prompt_version: str = ""
    provider: str = ""
    model_name: str | None = None
    provider_config_id: str | None = None
    ai_call_log_id: str | None = None
    id: str | None = None

    def to_contract_dict(self) -> dict[str, Any]:
        """输出 ``ReviewItemRead`` 的业务字段（Resource 公共字段由持久层补）。"""
        return {
            name: getattr(self, name)
            for name in (*REVIEW_ITEM_WRITE_FIELDS, *REVIEW_ITEM_READ_EXTRA_FIELDS)
        }


@dataclass(frozen=True)
class GenerationResult:
    """一次真实出题的结构化结果。"""

    items: list[ReviewItemDraft]
    knowledge_point_id: str
    question_types: list[str]
    prompt_version: str
    provider: str = ""
    model_name: str | None = None
    provider_config_id: str | None = None
    ai_call_log_id: str | None = None


@dataclass(frozen=True)
class GenerationPolicyResult:
    """版本化与人工修订保护的落库计划。"""

    to_insert: list[ReviewItemDraft]
    to_uncurrent: list[ReviewItemDraft]
    protected: list[ReviewItemDraft]


def build_generation_request(
    knowledge_point: Mapping[str, Any],
    strategy: SubjectStrategy,
    config: AIProviderConfig,
    *,
    question_types: Iterable[str] | None = None,
    count: int = 3,
    subject_name: str | None = None,
    prompt_version: str = PROMPT_VERSION_GENERATION,
) -> StructuredRequest:
    """构造出题请求（纯逻辑）。题型由学科偏好与请求交集决定。"""
    if not isinstance(count, int) or not (1 <= count <= 20):
        raise StructuredOutputError(
            "count 必须处于 1..20（契约 POST /review-items/generate）",
            details=[ErrorDetail("count", "out of range 1..20")],
        )
    types = resolve_question_types(strategy, question_types)
    system, user = build_generation_prompt(
        strategy,
        subject_name=subject_name or strategy.name,
        knowledge_title=str(knowledge_point.get("title") or ""),
        knowledge_body=str(knowledge_point.get("body") or ""),
        question_types=types,
        count=count,
        prompt_version=prompt_version,
    )
    return StructuredRequest(
        operation="generate_review_items",
        prompt_version=prompt_version,
        system=system,
        user=user,
        response_schema_hint=GENERATION_SCHEMA_HINT,
        temperature=config.temperature,
        metadata={
            "knowledge_point_id": str(knowledge_point.get("id") or ""),
            "slug": strategy.slug,
            "question_types": types,
            "count": count,
        },
    )


def parse_generation_output(
    result: Any,
    *,
    knowledge_point_id: str,
    meta: GenerationMeta | None = None,
) -> GenerationResult:
    """解析并校验模型输出为多题型题目列表（纯逻辑，绝不编造题目）。"""
    payload = _as_mapping(result)
    raw_items = payload.get("items")
    if raw_items is None and isinstance(payload, list):
        raw_items = payload
    if not isinstance(raw_items, list) or not raw_items:
        raise StructuredOutputError(
            "出题结果缺少非空的 items 数组，拒绝伪造题目",
            details=[ErrorDetail("items", "required non-empty array")],
        )
    meta = meta or GenerationMeta()
    items: list[ReviewItemDraft] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, Mapping):
            raise StructuredOutputError(f"items[{index}] 必须为对象")
        data: dict[str, Any] = dict(raw)
        data.setdefault("explanation", "")
        data.setdefault("summary", "")
        data.setdefault("options", None)
        assert_valid(data, validate_review_item, label=f"items[{index}]")
        items.append(
            ReviewItemDraft(
                knowledge_point_id=knowledge_point_id,
                question_type=data["question_type"],
                question=data["question"],
                answer=data["answer"],
                explanation=data["explanation"],
                summary=data["summary"],
                options=list(data["options"]) if data["options"] is not None else None,
                item_version=1,
                is_current=True,
                prompt_version=meta.prompt_version,
                provider=meta.provider,
                model_name=meta.model_name,
                provider_config_id=meta.provider_config_id,
                ai_call_log_id=meta.ai_call_log_id,
            )
        )
    return GenerationResult(
        items=items,
        knowledge_point_id=knowledge_point_id,
        question_types=sorted({item.question_type for item in items}),
        prompt_version=meta.prompt_version,
        provider=meta.provider,
        model_name=meta.model_name,
        provider_config_id=meta.provider_config_id,
        ai_call_log_id=meta.ai_call_log_id,
    )


def apply_generation_policy(
    existing: Iterable[ReviewItemDraft],
    drafts: Iterable[ReviewItemDraft],
) -> GenerationPolicyResult:
    """版本化 + 人工编辑保护（FR-04）。

    - ``item_version`` 按 ``(knowledge_point_id, question_type)`` 递增，
      对齐契约唯一约束 ``UQ(knowledge_point_id, question_type, item_version)``。
    - 同键旧 current 置 ``is_current=False``，旧版保留。
    - 若旧 current 为 ``manual_revision=True``，新版本仍写入但不抢占
      ``is_current``（人工编辑不被覆盖）。
    """
    max_version: dict[tuple[str, str], int] = {}
    original_currents: dict[tuple[str, str], ReviewItemDraft] = {}
    for item in existing:
        key = (item.knowledge_point_id, item.question_type)
        max_version[key] = max(max_version.get(key, 0), item.item_version)
        if item.is_current:
            original_currents[key] = item

    to_insert: list[ReviewItemDraft] = []
    to_uncurrent: list[ReviewItemDraft] = []
    protected: list[ReviewItemDraft] = []
    handled_keys: set[tuple[str, str]] = set()
    for draft in drafts:
        key = (draft.knowledge_point_id, draft.question_type)
        next_version = max_version.get(key, 0) + 1
        max_version[key] = next_version
        original = original_currents.get(key)
        is_current = True
        if key not in handled_keys and original is not None:
            # 只下架「已存在」的旧 current；同批次新题之间互不抢占。
            if original.manual_revision:
                protected.append(original)
                is_current = False
            else:
                to_uncurrent.append(replace(original, is_current=False))
            handled_keys.add(key)
        elif original is not None and original.manual_revision:
            is_current = False
        to_insert.append(
            replace(draft, item_version=next_version, is_current=is_current)
        )
    return GenerationPolicyResult(
        to_insert=to_insert,
        to_uncurrent=to_uncurrent,
        protected=protected,
    )


class QuestionGenerator:
    """把真实 Provider 调用、结构化解析与版本策略串起来的用例。"""

    def __init__(self, executor: "AIExecutionService") -> None:
        self._executor = executor

    def generate(
        self,
        knowledge_point: Mapping[str, Any],
        strategy: SubjectStrategy,
        config: AIProviderConfig,
        *,
        question_types: Iterable[str] | None = None,
        count: int = 3,
        subject_name: str | None = None,
    ) -> GenerationResult:
        kp_id = str(knowledge_point.get("id") or "")
        if not kp_id:
            raise StructuredOutputError("出题必须指定 knowledge_point_id")
        request = build_generation_request(
            knowledge_point,
            strategy,
            config,
            question_types=question_types,
            count=count,
            subject_name=subject_name or strategy.name,
        )
        completed = self._executor.complete(config, request)
        meta = GenerationMeta.from_call(completed.result, completed.call_log)
        meta = replace(meta, prompt_version=request.prompt_version)
        return parse_generation_output(
            completed.result, knowledge_point_id=kp_id, meta=meta
        )
