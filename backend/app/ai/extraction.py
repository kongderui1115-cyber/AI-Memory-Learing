"""笔记理解 → 结构化知识点提取 / 整理（AI-03 / FR-02、FR-03）。

对外只依赖 ``AIProvider`` 端口与通用调用执行器；本模块的核心（请求构造、
结构化输出解析与校验、去重、合并、人工修订保护）全部为纯标准库函数，
可独立单元测试。

缺 Key 或计费未授权时，调用执行器会抛 CONFIG_MISSING；本模块**不会**在
解析失败时编造任何知识点，一律抛 ``StructuredOutputError``。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, TYPE_CHECKING

from .config import AIProviderConfig
from .errors import ErrorDetail, StructuredOutputError
from .ports import GenerationMeta, ProviderResult, StructuredRequest
from .prompts import (
    EXTRACTION_SCHEMA_HINT,
    PROMPT_VERSION_EXTRACTION,
    build_extraction_prompt,
)
from .strategies import SubjectStrategy
from .validation import (
    KNOWLEDGE_POINT_WRITE_FIELDS,
    assert_valid,
    canonical_hash,
    validate_knowledge_point,
)

if TYPE_CHECKING:  # 仅类型标注，运行时不引入 service 依赖
    from .service import AIExecutionService


@dataclass(frozen=True)
class KnowledgePointDraft:
    """对齐 ``KnowledgePointWrite``，附去重/生命周期/来源元数据。"""

    subject_id: str
    title: str
    body: str
    summary: str
    difficulty: int
    keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = "draft"
    canonical_hash: str = ""
    manual_revision: bool = False
    merged_into_id: str | None = None
    id: str | None = None
    source_raw_note_id: str = ""
    prompt_version: str = ""
    provider: str = ""
    model_name: str | None = None
    provider_config_id: str | None = None
    ai_call_log_id: str | None = None

    def to_contract_dict(self) -> dict[str, Any]:
        """只输出 ``KnowledgePointWrite`` 契约字段。"""
        return {name: getattr(self, name) for name in KNOWLEDGE_POINT_WRITE_FIELDS}

    def to_row_dict(self) -> dict[str, Any]:
        """输出落库字段（含 canonical_hash / manual_revision / 来源）。"""
        data = self.to_contract_dict()
        data.update(
            {
                "canonical_hash": self.canonical_hash,
                "manual_revision": self.manual_revision,
                "merged_into_id": self.merged_into_id,
                "id": self.id,
                "source_raw_note_id": self.source_raw_note_id,
                "prompt_version": self.prompt_version,
                "provider": self.provider,
                "model_name": self.model_name,
                "provider_config_id": self.provider_config_id,
                "ai_call_log_id": self.ai_call_log_id,
            }
        )
        return data


@dataclass(frozen=True)
class ExtractionResult:
    """一次真实抽取的结构化结果。"""

    points: list[KnowledgePointDraft]
    subject_id: str
    source_raw_note_id: str
    prompt_version: str
    provider: str = ""
    model_name: str | None = None
    provider_config_id: str | None = None
    ai_call_log_id: str | None = None


@dataclass(frozen=True)
class ReconcileResult:
    """再同步时与已有知识点的对账结果（FR-03 去重/合并/人工修订保护）。"""

    to_create: list[KnowledgePointDraft]
    to_update: list[KnowledgePointDraft]
    protected: list[KnowledgePointDraft]
    merged: list[KnowledgePointDraft]


def build_extraction_request(
    note: Mapping[str, Any],
    strategy: SubjectStrategy,
    config: AIProviderConfig,
    *,
    subject_name: str,
    prompt_version: str = PROMPT_VERSION_EXTRACTION,
    schema_hint: dict[str, Any] | None = None,
) -> StructuredRequest:
    """构造知识点抽取请求（纯逻辑）。"""
    system, user = build_extraction_prompt(
        strategy,
        subject_name=subject_name,
        note_title=str(note.get("title") or ""),
        note_content=str(note.get("content_markdown") or note.get("content") or ""),
        prompt_version=prompt_version,
        schema_hint=schema_hint,
    )
    return StructuredRequest(
        operation="extract_knowledge",
        prompt_version=prompt_version,
        system=system,
        user=user,
        response_schema_hint=EXTRACTION_SCHEMA_HINT if schema_hint is None else schema_hint,
        temperature=config.temperature,
        metadata={
            "subject_id": strategy.subject_id,
            "slug": strategy.slug,
            "source_raw_note_id": str(note.get("id") or ""),
        },
    )


def _as_mapping(result: ProviderResult | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(result, ProviderResult):
        if result.parsed is None:
            raise StructuredOutputError(
                "Provider 未返回可解析的 JSON 结构化结果，拒绝伪造知识点",
                details=[ErrorDetail("parsed", "null structured output")],
            )
        return result.parsed
    if isinstance(result, Mapping):
        return result
    raise StructuredOutputError("抽取结果类型非法，期望 mapping 或 ProviderResult")


def parse_extraction_output(
    result: ProviderResult | Mapping[str, Any],
    *,
    subject_id: str,
    source_raw_note_id: str,
    meta: GenerationMeta | None = None,
) -> ExtractionResult:
    """解析并校验模型结构化输出为知识点列表（纯逻辑，绝不编造内容）。"""
    payload = _as_mapping(result)
    raw_points = payload.get("knowledge_points")
    if raw_points is None and isinstance(payload, list):
        raw_points = payload
    if not isinstance(raw_points, list) or not raw_points:
        raise StructuredOutputError(
            "抽取结果缺少非空的 knowledge_points 数组，拒绝伪造知识点",
            details=[ErrorDetail("knowledge_points", "required non-empty array")],
        )

    meta = meta or GenerationMeta()
    points: list[KnowledgePointDraft] = []
    for index, raw in enumerate(raw_points):
        if not isinstance(raw, Mapping):
            raise StructuredOutputError(f"knowledge_points[{index}] 必须为对象")
        data: dict[str, Any] = dict(raw)
        # 学科由调用方指定、自动抽取的知识点状态固定为 draft（激活是独立端点），
        # 二者都不允许模型输出伪造；其余可选字段按契约默认补齐。
        data["subject_id"] = subject_id
        data["status"] = "draft"
        data.setdefault("summary", "")
        data.setdefault("keywords", [])
        data.setdefault("tags", [])
        assert_valid(data, validate_knowledge_point, label=f"knowledge_points[{index}]")
        digest = canonical_hash(data["title"], data["body"])
        points.append(
            KnowledgePointDraft(
                subject_id=data["subject_id"],
                title=data["title"],
                body=data["body"],
                summary=data["summary"],
                difficulty=data["difficulty"],
                keywords=list(data["keywords"]),
                tags=list(data["tags"]),
                status=data["status"],
                canonical_hash=digest,
                source_raw_note_id=source_raw_note_id,
                prompt_version=meta.prompt_version,
                provider=meta.provider,
                model_name=meta.model_name,
                provider_config_id=meta.provider_config_id,
                ai_call_log_id=meta.ai_call_log_id,
            )
        )
    return ExtractionResult(
        points=points,
        subject_id=subject_id,
        source_raw_note_id=source_raw_note_id,
        prompt_version=meta.prompt_version,
        provider=meta.provider,
        model_name=meta.model_name,
        provider_config_id=meta.provider_config_id,
        ai_call_log_id=meta.ai_call_log_id,
    )


def dedupe_knowledge_points(
    points: Iterable[KnowledgePointDraft],
) -> list[KnowledgePointDraft]:
    """按 ``canonical_hash`` 去重，保留首次出现（幂等，不产生重复知识点）。"""
    seen: set[str] = set()
    unique: list[KnowledgePointDraft] = []
    for point in points:
        if point.canonical_hash in seen:
            continue
        seen.add(point.canonical_hash)
        unique.append(point)
    return unique


def merge_knowledge_points(
    target: KnowledgePointDraft,
    sources: Iterable[KnowledgePointDraft],
    *,
    reason: str = "",
) -> list[KnowledgePointDraft]:
    """把若干知识点合并到目标：源标记为 ``merged`` 终态并设置 ``merged_into_id``。

    对齐契约生命周期 ``draft|active → merged``，merged 终态只读。
    ``reason`` 仅记录于返回结果，不修改契约字段。``target.id`` 为 UUID，
    对齐契约 ``knowledge_points.merged_into_id uuid FK``。
    """
    if not target.id:
        raise StructuredOutputError(
            "合并目标必须提供 UUID id（merged_into_id 需要引用目标知识点）",
            details=[ErrorDetail("target_id", "required uuid")],
        )
    merged: list[KnowledgePointDraft] = []
    for source in sources:
        if source.status == "merged":
            raise StructuredOutputError("已合并的知识点不可再次合并（终态只读）")
        merged.append(replace(source, status="merged", merged_into_id=target.id))
    return merged


def reconcile_knowledge_points(
    existing: Iterable[KnowledgePointDraft],
    incoming: Iterable[KnowledgePointDraft],
) -> ReconcileResult:
    """再同步对账：去重、合并已存在项、保护人工修订。

    - 相同 ``canonical_hash``：已存在项若为 ``merged`` 或 ``manual_revision``
      则跳过（绝不覆盖人工修订与终态）；否则合并 keywords/tags 后更新。
    - 新哈希：创建。
    """
    by_hash: dict[str, KnowledgePointDraft] = {}
    for point in existing:
        by_hash.setdefault(point.canonical_hash, point)

    to_create: list[KnowledgePointDraft] = []
    to_update: list[KnowledgePointDraft] = []
    protected: list[KnowledgePointDraft] = []
    merged: list[KnowledgePointDraft] = []

    for point in dedupe_knowledge_points(incoming):
        current = by_hash.get(point.canonical_hash)
        if current is None:
            to_create.append(point)
            by_hash[point.canonical_hash] = point
            continue
        if current.status == "merged":
            merged.append(current)
            continue
        if current.manual_revision:
            protected.append(current)
            continue
        to_update.append(
            replace(
                current,
                keywords=sorted(set(current.keywords) | set(point.keywords)),
                tags=sorted(set(current.tags) | set(point.tags)),
                source_raw_note_id=point.source_raw_note_id,
            )
        )
    return ReconcileResult(
        to_create=to_create,
        to_update=to_update,
        protected=protected,
        merged=merged,
    )


class KnowledgeExtractor:
    """把真实 Provider 调用与结构化整理串起来的用例。

    ``executor`` 为具备 ``complete(config, request)`` 的对象（生产为
    ``AIExecutionService``）。未配置凭据时该调用抛 CONFIG_MISSING，
    本类不捕获、不降级、不伪造结果。
    """

    def __init__(self, executor: "AIExecutionService") -> None:
        self._executor = executor

    def extract(
        self,
        note: Mapping[str, Any],
        strategy: SubjectStrategy,
        config: AIProviderConfig,
        *,
        subject_id: str | None = None,
        subject_name: str | None = None,
    ) -> ExtractionResult:
        sid = subject_id or strategy.subject_id
        if not sid:
            raise StructuredOutputError("抽取必须指定 subject_id")
        request = build_extraction_request(
            note,
            strategy,
            config,
            subject_name=subject_name or strategy.name,
        )
        completed = self._executor.complete(config, request)
        meta = GenerationMeta.from_call(completed.result, completed.call_log)
        meta = replace(meta, prompt_version=request.prompt_version)
        return parse_extraction_output(
            completed.result,
            subject_id=sid,
            source_raw_note_id=str(note.get("id") or ""),
            meta=meta,
        )
