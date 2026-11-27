"""每日复习任务生成纯逻辑（BE-06 / FR-06）。

**领域层纯函数**：只依赖标准库，不连接数据库、不读系统时钟、不写库。
"今天"由调用方以 UTC ``as_of`` 传入，``local_date`` / ``timezone`` 作为批次
元数据与幂等键的一部分记录，从而完全确定、可复现、可测试。

覆盖需求：
- 到期筛选：``due_at <= as_of`` 即入选；逾期项 due 更早，天然滚入（补漏，due 不丢失）；
- 学科过滤：``subject_id`` 为 None 表示全部，否则只保留该学科；
- 优先级：逾期越久 > 遗忘次数越多 > 难度越高 > 优先级提示 > due 越早 > ID 升序（确定 tie-break）；
- 每日期望上限：``daily_limit``（契约 1..500）截断；
- 幂等：idempotency_key = ``user:local_date:subject-or-all:policy-hash``；
  同 key 重放返回原批次（``replayed=True``），且已存在任务的知识点不重复生成；
- 漏复习滚动：上一批次未完成（pending/in_progress）任务经 ``carry_over`` 
  传入后必入选，``scheduled_due_at`` 保留原 due。

返回的 ``DailyBatchPlan`` / ``DailyTaskPlan`` 是纯逻辑计划对象，由 services 层
映射为 ``daily_review_batches`` / ``daily_review_tasks`` 落库。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Any, Sequence

RANKING_VERSION = "daily-ranking-1"
SECONDS_PER_DAY = 86400.0
MIN_DAILY_LIMIT = 1
MAX_DAILY_LIMIT = 500  # 契约 DailyGenerateRequest.daily_limit: 1..500
UNFINISHED_STATUSES: tuple[str, ...] = ("pending", "in_progress")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("必须是 datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("必须是带时区的 UTC datetime（禁止 naive datetime）")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat()


def _overdue_days(due_at: datetime, as_of: datetime) -> float:
    return max((_utc(as_of) - _utc(due_at)).total_seconds() / SECONDS_PER_DAY, 0.0)


# ---- 输入 / 输出数据结构 ----
@dataclass(frozen=True)
class DueCandidate:
    """一个待生成任务的到期知识点候选（来自 schedule_states + knowledge_points）。"""

    knowledge_point_id: str
    due_at: datetime  # UTC 带时区
    subject_id: str | None = None
    difficulty: int = 3  # 1..5
    lapse_count: int = 0
    retrievability: float | None = None
    review_item_id: str | None = None
    priority_hint: int = 0


@dataclass(frozen=True)
class DailyTaskPlan:
    """纯逻辑生成的单条任务计划。"""

    knowledge_point_id: str
    review_item_id: str | None
    scheduled_due_at: datetime  # 保留原 due，补漏不刷新
    priority: int
    position: int  # 1-based
    status: str = "pending"
    carried_over: bool = False
    subject_id: str | None = None
    difficulty: int = 3
    lapse_count: int = 0
    priority_hint: int = 0
    priority_explanation: dict[str, Any] | None = None

    def to_candidate(self) -> DueCandidate:
        """滚动到次日时把任务还原为候选（保留原 due 与优先级因子）。"""
        return DueCandidate(
            knowledge_point_id=self.knowledge_point_id,
            due_at=self.scheduled_due_at,
            subject_id=self.subject_id,
            difficulty=self.difficulty,
            lapse_count=self.lapse_count,
            review_item_id=self.review_item_id,
            priority_hint=self.priority_hint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_point_id": self.knowledge_point_id,
            "review_item_id": self.review_item_id,
            "scheduled_due_at": _iso(self.scheduled_due_at),
            "priority": self.priority,
            "position": self.position,
            "status": self.status,
            "carried_over": self.carried_over,
            "priority_explanation": dict(self.priority_explanation or {}),
        }


@dataclass(frozen=True)
class DailyBatchPlan:
    """纯逻辑生成的批次计划（幂等重放会置 ``replayed=True``）。"""

    idempotency_key: str
    local_date: date
    timezone: str
    subject_id: str | None
    daily_limit: int
    status: str
    generated_at: datetime
    tasks: tuple[DailyTaskPlan, ...]
    policy_hash: str
    replayed: bool = False

    def knowledge_point_ids(self) -> frozenset[str]:
        return frozenset(task.knowledge_point_id for task in self.tasks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "local_date": self.local_date.isoformat(),
            "timezone": self.timezone,
            "subject_id": self.subject_id,
            "daily_limit": self.daily_limit,
            "status": self.status,
            "generated_at": _iso(self.generated_at),
            "policy_hash": self.policy_hash,
            "replayed": self.replayed,
            "tasks": [task.to_dict() for task in self.tasks],
        }


# ---- 幂等键与策略哈希 ----
def policy_hash(
    *,
    local_date: date,
    timezone_name: str,
    subject_id: str | None,
    daily_limit: int,
    ranking_version: str = RANKING_VERSION,
) -> str:
    """策略哈希：确定性短摘要（24 hex），作为幂等键的 policy-hash 部分。"""
    canonical = {
        "local_date": local_date.isoformat(),
        "timezone": timezone_name,
        "subject_id": subject_id or "all",
        "daily_limit": daily_limit,
        "ranking_version": ranking_version,
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def make_idempotency_key(
    user_id: str,
    local_date: date,
    subject_id: str | None,
    policy_hash_value: str,
) -> str:
    """契约 key 格式 ``user:local_date:subject-or-all:policy-hash``（长度 <=128）。"""
    return f"{user_id}:{local_date.isoformat()}:{subject_id or 'all'}:{policy_hash_value}"


# ---- 筛选 / 排序 / 优先级 ----
def select_due(
    candidates: Sequence[DueCandidate],
    as_of: datetime,
    subject_id: str | None = None,
) -> list[DueCandidate]:
    """到期筛选 + 学科过滤：``due_at <= as_of`` 入选（逾期项自动滚入，补漏不丢失）。"""
    as_of_utc = _utc(as_of)
    result = []
    for candidate in candidates:
        _utc(candidate.due_at)  # 校验带时区
        if _utc(candidate.due_at) > as_of_utc:
            continue
        if subject_id is not None and candidate.subject_id != subject_id:
            continue
        result.append(candidate)
    return result


def _sort_key(candidate: DueCandidate, as_of_utc: datetime) -> tuple[Any, ...]:
    overdue = _overdue_days(candidate.due_at, as_of_utc)
    return (
        -overdue,  # 逾期越久越优先
        -candidate.lapse_count,
        -candidate.difficulty,
        -candidate.priority_hint,
        _utc(candidate.due_at).timestamp(),  # due 越早越优先
        candidate.knowledge_point_id,  # 确定性 tie-break
    )


def rank_candidates(candidates: Sequence[DueCandidate], as_of: datetime) -> list[DueCandidate]:
    """按优先级规则确定性排序（含稳定 tie-break，保证可复现）。"""
    as_of_utc = _utc(as_of)
    return sorted(candidates, key=lambda c: _sort_key(c, as_of_utc))


def compute_priority(candidate: DueCandidate, as_of: datetime) -> tuple[int, dict[str, Any]]:
    """计算整数优先级与可解释依据（不与 position 耦合，确定性）。"""
    as_of_utc = _utc(as_of)
    overdue = _overdue_days(candidate.due_at, as_of_utc)
    priority = (
        min(int(overdue), 30) * 100
        + min(max(candidate.lapse_count, 0), 10) * 10
        + candidate.difficulty
        + candidate.priority_hint
    )
    explanation = {
        "overdue_days": round(overdue, 6),
        "lapse_count": candidate.lapse_count,
        "difficulty": candidate.difficulty,
        "priority_hint": candidate.priority_hint,
        "due_at": _iso(candidate.due_at),
        "formula": "min(逾期天数,30)*100 + min(遗忘次数,10)*10 + 难度 + 优先级提示",
        "reason": (
            f"逾期 {overdue:.2f} 天、遗忘 {candidate.lapse_count} 次、难度 {candidate.difficulty}，"
            f"按规则得优先级 {priority}。"
        ),
    }
    return priority, explanation


def unfinished_tasks(
    previous_tasks: Sequence[DailyTaskPlan],
    completed_knowledge_point_ids: frozenset[str] | set[str] = frozenset(),
) -> list[DailyTaskPlan]:
    """上一批次中未完成（pending / in_progress）且未后来完成的任务，用于次日滚动。"""
    return [
        task for task in previous_tasks
        if task.status in UNFINISHED_STATUSES
        and task.knowledge_point_id not in completed_knowledge_point_ids
    ]


# ---- 顶层生成（幂等） ----
def generate_daily_batch(
    *,
    user_id: str,
    local_date: date,
    timezone_name: str,
    as_of: datetime,
    candidates: Sequence[DueCandidate],
    daily_limit: int = 30,
    subject_id: str | None = None,
    carry_over: Sequence[DailyTaskPlan] = (),
    existing_plan: DailyBatchPlan | None = None,
    existing_task_knowledge_point_ids: frozenset[str] | set[str] = frozenset(),
    ranking_version: str = RANKING_VERSION,
) -> DailyBatchPlan:
    """生成当日复习批次（纯函数、确定、幂等）。

    - 相同 ``(user_id, local_date, subject, policy)`` 且传入 ``existing_plan``
      时直接重放原批次，不新增任何任务；
    - ``existing_task_knowledge_point_ids`` 进一步保证同批次内知识点不重复；
    - ``carry_over`` 中的漏复习任务必入选并保留原 due。
    """
    as_of_utc = _utc(as_of)
    if not MIN_DAILY_LIMIT <= daily_limit <= MAX_DAILY_LIMIT:
        raise ValueError(f"daily_limit 必须位于 {MIN_DAILY_LIMIT}..{MAX_DAILY_LIMIT}")
    if not isinstance(local_date, date):
        raise TypeError("local_date 必须是 datetime.date")

    ph = policy_hash(
        local_date=local_date,
        timezone_name=timezone_name,
        subject_id=subject_id,
        daily_limit=daily_limit,
        ranking_version=ranking_version,
    )
    key = make_idempotency_key(user_id, local_date, subject_id, ph)

    # 幂等重放：同 key 直接返回原资源。
    if existing_plan is not None and existing_plan.idempotency_key == key:
        return replace(existing_plan, replayed=True)

    # 合并正常到期候选与滚动补漏任务，按知识点去重（保留更早 due）。
    pool: dict[str, tuple[DueCandidate, bool]] = {}
    for candidate in candidates:
        _utc(candidate.due_at)
        pool[candidate.knowledge_point_id] = (candidate, False)
    for task in carry_over:
        converted = task.to_candidate()
        prior = pool.get(converted.knowledge_point_id)
        if prior is None:
            pool[converted.knowledge_point_id] = (converted, True)
        else:
            earlier = min(prior[0], converted, key=lambda c: _utc(c.due_at))
            pool[converted.knowledge_point_id] = (earlier, True)

    merged = [item[0] for item in pool.values()]
    carried_map = {candidate.knowledge_point_id: carried for candidate, carried in pool.values()}

    selected = select_due(merged, as_of_utc, subject_id)
    existing_ids = set(existing_task_knowledge_point_ids)
    selected = [c for c in selected if c.knowledge_point_id not in existing_ids]
    ranked = rank_candidates(selected, as_of_utc)[:daily_limit]

    tasks: list[DailyTaskPlan] = []
    for position, candidate in enumerate(ranked, start=1):
        priority, explanation = compute_priority(candidate, as_of_utc)
        tasks.append(
            DailyTaskPlan(
                knowledge_point_id=candidate.knowledge_point_id,
                review_item_id=candidate.review_item_id,
                scheduled_due_at=_utc(candidate.due_at),
                priority=priority,
                position=position,
                status="pending",
                carried_over=carried_map.get(candidate.knowledge_point_id, False),
                subject_id=candidate.subject_id,
                difficulty=candidate.difficulty,
                lapse_count=candidate.lapse_count,
                priority_hint=candidate.priority_hint,
                priority_explanation=explanation,
            )
        )

    return DailyBatchPlan(
        idempotency_key=key,
        local_date=local_date,
        timezone=timezone_name,
        subject_id=subject_id,
        daily_limit=daily_limit,
        status="ready",
        generated_at=as_of_utc,
        tasks=tuple(tasks),
        policy_hash=ph,
        replayed=False,
    )


__all__ = [
    "RANKING_VERSION", "MIN_DAILY_LIMIT", "MAX_DAILY_LIMIT",
    "DueCandidate", "DailyTaskPlan", "DailyBatchPlan",
    "policy_hash", "make_idempotency_key", "select_due", "rank_candidates",
    "compute_priority", "unfinished_tasks", "generate_daily_batch",
]
