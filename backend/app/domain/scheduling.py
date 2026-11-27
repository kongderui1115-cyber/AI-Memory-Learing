"""复习调度纯函数（BE-05 / FR-05）。

本模块是**领域层纯逻辑**：只依赖 Python 标准库，不依赖 FastAPI / SQLAlchemy /
pydantic / 数据库 / 系统时钟 / 随机数 / 外部 API。所有函数的输出完全由
``(state, rating, reviewed_at, parameters)`` 决定，可复现、可对照、可解释。

实现两套可切换策略，取值与 ``app/contracts/enums.py`` 对齐（此处用字符串常量
避免导入会拉起 pydantic 的契约包，保持领域层零第三方依赖）：

* ``ebbinghaus`` 艾宾浩斯固定间隔：可配置间隔序列（默认 1/2/4/7/15/30 天），
  按复习次数推进；``again`` 归零到首档，``hard`` 停留，``good`` +1，
  ``easy`` +2；超出序列沿用末项。
* ``fsrs`` 自适应调度：维护记忆三态 stability / difficulty / retrievability，
  采用幂律遗忘曲线 ``R(t) = (1 + FACTOR * t / S) ** DECAY``，按目标留存率
  ``target_retention`` 反解下次间隔，评分 again/hard/good/easy 作为确定性输入
  更新状态。参数全部经 ``parameters`` 快照保存，防止配置变化篡改历史。

"为什么今天复习"：:func:`explain` 与每次 :func:`review` 的
``last_calculation`` 均给出结构化、中文可读的计算依据与输入快照。

时间统一使用 UTC、带时区的 ``datetime``；naive datetime 一律明确报错。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

# ---- 契约取值（与 app/contracts/enums.py 一致，保持领域层独立） ----
EBBINGHAUS = "ebbinghaus"
FSRS = "fsrs"
SUPPORTED_STRATEGIES: tuple[str, ...] = (EBBINGHAUS, FSRS)

AGAIN = "again"
HARD = "hard"
GOOD = "good"
EASY = "easy"
RATING_VALUES: tuple[str, ...] = (AGAIN, HARD, GOOD, EASY)
RATING_TO_INT: dict[str, int] = {AGAIN: 1, HARD: 2, GOOD: 3, EASY: 4}

EBBINGHAUS_ALGORITHM_VERSION = "ebbinghaus-fixed-1"
FSRS_ALGORITHM_VERSION = "fsrs-parametric-1"

SECONDS_PER_DAY = 86400.0


# ---- 默认参数（确定性；可通过 parameters 覆盖并快照进 state） ----
def default_ebbinghaus_parameters() -> dict[str, Any]:
    """返回全新副本，避免共享可变默认值。"""
    return {"intervals_days": [1, 2, 4, 7, 15, 30]}


def default_fsrs_parameters() -> dict[str, Any]:
    """FSRS 风格参数化自适应调度的确定性默认参数。

    decay=-0.5 时 FACTOR = 0.9**(1/decay) - 1，使 R(S)=0.9，即 stability
    定义为"留存率降到 0.9 所需天数"。其余参数命名清晰、均可被覆盖。
    """
    return {
        "decay": -0.5,
        "target_retention": 0.9,
        "initial_stability_days": {"again": 0.5, "hard": 1.5, "good": 3.5, "easy": 10.0},
        "initial_difficulty": 5.0,
        "difficulty_delta": 0.9,
        "mean_reversion": 0.05,
        "stability_gain": 1.6,
        "stability_exponent": 0.14,
        "retrievability_gain": 1.0,
        "hard_penalty": 0.8,
        "easy_bonus": 1.3,
        "lapse_stability_multiplier": 0.5,
        "lapse_difficulty_delta": 1.0,
        "min_stability_days": 0.1,
    }


def default_parameters(strategy: str) -> dict[str, Any]:
    validate_strategy(strategy)
    return default_ebbinghaus_parameters() if strategy == EBBINGHAUS else default_fsrs_parameters()


def _merge_parameters(strategy: str, provided: Mapping[str, Any] | None) -> dict[str, Any]:
    """以默认参数为底，用提供的参数覆盖，并校验取值合法性。"""
    params = default_parameters(strategy)
    if provided:
        for key, value in provided.items():
            if value is not None:
                params[key] = value
    if strategy == EBBINGHAUS:
        intervals = params.get("intervals_days")
        if not isinstance(intervals, (list, tuple)) or not intervals:
            raise ValueError("ebbinghaus 参数 intervals_days 必须为非空序列")
        parsed = [float(day) for day in intervals]
        if any(day <= 0 for day in parsed):
            raise ValueError("ebbinghaus 参数 intervals_days 必须全为正数")
        params["intervals_days"] = parsed
    else:
        decay = float(params["decay"])
        if decay >= 0:
            raise ValueError("fsrs 参数 decay 必须为负数")
        retention = float(params["target_retention"])
        if not 0.0 < retention < 1.0:
            raise ValueError("fsrs 参数 target_retention 必须位于 (0, 1)")
        for key in ("initial_stability_days",):
            table = params.get(key)
            if not isinstance(table, Mapping) or any(r not in table for r in RATING_VALUES):
                raise ValueError(f"fsrs 参数 {key} 必须包含 again/hard/good/easy 四项")
    return params


# ---- 校验与时间工具 ----
def validate_strategy(strategy: str) -> None:
    if strategy not in SUPPORTED_STRATEGIES:
        raise ValueError(f"不支持的调度策略: {strategy!r}，可选 {SUPPORTED_STRATEGIES}")


def validate_rating(rating: str) -> None:
    if rating not in RATING_VALUES:
        raise ValueError(f"不支持的复习评分: {rating!r}，可选 {RATING_VALUES}")


def _require_aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} 必须是 datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} 必须是带时区的 UTC datetime（禁止 naive datetime）")
    return value.astimezone(timezone.utc)


def _to_utc(value: datetime) -> datetime:
    return _require_aware(value, "datetime")


def _iso(value: datetime) -> str:
    return _to_utc(value).isoformat()


def _parse_dt(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return _to_utc(value)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise TypeError(f"无法解析时间: {value!r}")


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _elapsed_days(start: datetime, end: datetime) -> float:
    return max((_to_utc(end) - _to_utc(start)).total_seconds() / SECONDS_PER_DAY, 0.0)


# ---- 记忆数学模型（公开，便于独立验证与复现） ----
def fsrs_factor(decay: float = -0.5) -> float:
    """遗忘曲线系数：使 ``R(t=stability) = 0.9``。"""
    if decay >= 0:
        raise ValueError("decay 必须为负数")
    return pow(0.9, 1.0 / decay) - 1.0


def retrievability_curve(stability_days: float, elapsed_days: float, decay: float = -0.5) -> float:
    """幂律遗忘曲线 ``R(t) = (1 + FACTOR * t / S) ** DECAY``，结果裁剪到 [0,1]。"""
    if stability_days <= 0:
        return 0.0
    factor = fsrs_factor(decay)
    t = max(elapsed_days, 0.0)
    value = (1.0 + factor * t / stability_days) ** decay
    return _clamp(value, 0.0, 1.0)


def interval_for_retention(stability_days: float, target_retention: float, decay: float = -0.5) -> float:
    """按目标留存率反解间隔：``I = S / FACTOR * (retention**(1/DECAY) - 1)``。

    当 ``target_retention == 0.9`` 时恒有 ``I == S``（由 FACTOR 定义保证）。
    """
    if not 0.0 < target_retention < 1.0:
        raise ValueError("target_retention 必须位于 (0, 1)")
    factor = fsrs_factor(decay)
    return max(0.0, stability_days / factor * (pow(target_retention, 1.0 / decay) - 1.0))


# ---- 领域状态（字段与 ScheduleStateRead 契约对齐） ----
@dataclass(frozen=True)
class ScheduleState:
    """单个知识点的调度状态快照。字段与 ``ScheduleStateRead`` 一一对应。"""

    strategy: str
    due_at: datetime
    last_reviewed_at: datetime | None
    review_count: int
    lapse_count: int
    interval_index: int
    interval_days: float | None
    stability: float | None
    difficulty: float | None
    retrievability: float | None
    target_retention: float | None
    algorithm_version: str
    parameters: dict[str, Any]
    last_calculation: dict[str, Any]
    strategy_changed_at: datetime


def to_dict(state: ScheduleState) -> dict[str, Any]:
    """序列化为可 JSON 化字典（用于 jsonb / ScheduleProjection.state）。"""
    return {
        "strategy": state.strategy,
        "due_at": _iso(state.due_at),
        "last_reviewed_at": _iso(state.last_reviewed_at) if state.last_reviewed_at else None,
        "review_count": state.review_count,
        "lapse_count": state.lapse_count,
        "interval_index": state.interval_index,
        "interval_days": state.interval_days,
        "stability": state.stability,
        "difficulty": state.difficulty,
        "retrievability": state.retrievability,
        "target_retention": state.target_retention,
        "algorithm_version": state.algorithm_version,
        "parameters": dict(state.parameters),
        "last_calculation": dict(state.last_calculation),
        "strategy_changed_at": _iso(state.strategy_changed_at),
    }


def from_mapping(data: Mapping[str, Any]) -> ScheduleState:
    """从 ORM 行 / ScheduleStateRead 字典构造领域状态（services 层使用）。"""
    return ScheduleState(
        strategy=str(data["strategy"]),
        due_at=_parse_dt(data["due_at"]),
        last_reviewed_at=_parse_dt(data["last_reviewed_at"]) if data.get("last_reviewed_at") else None,
        review_count=int(data.get("review_count", 0)),
        lapse_count=int(data.get("lapse_count", 0)),
        interval_index=int(data.get("interval_index", 0)),
        interval_days=float(data["interval_days"]) if data.get("interval_days") is not None else None,
        stability=float(data["stability"]) if data.get("stability") is not None else None,
        difficulty=float(data["difficulty"]) if data.get("difficulty") is not None else None,
        retrievability=float(data["retrievability"]) if data.get("retrievability") is not None else None,
        target_retention=float(data["target_retention"]) if data.get("target_retention") is not None else None,
        algorithm_version=str(data.get("algorithm_version", "")),
        parameters=dict(data.get("parameters") or {}),
        last_calculation=dict(data.get("last_calculation") or {}),
        strategy_changed_at=_parse_dt(data["strategy_changed_at"]) if data.get("strategy_changed_at") else _parse_dt(data["due_at"]),
    )


# ---- 初始化 ----
def initial_state(
    strategy: str,
    now: datetime,
    parameters: Mapping[str, Any] | None = None,
) -> ScheduleState:
    """激活知识点时建立独立调度状态。``now`` 为 UTC 带时区时间。"""
    validate_strategy(strategy)
    now_utc = _to_utc(now)
    params = _merge_parameters(strategy, parameters)

    if strategy == EBBINGHAUS:
        intervals = params["intervals_days"]
        first = float(intervals[0])
        due = now_utc + timedelta(days=first)
        calc = {
            "strategy": EBBINGHAUS,
            "reason": f"艾宾浩斯固定间隔初始化：首档 {first} 天后进行第一次复习。",
            "intervals_days": list(intervals),
            "interval_index": 0,
            "interval_days": first,
            "due_at": _iso(due),
        }
        return ScheduleState(
            strategy=EBBINGHAUS,
            due_at=due,
            last_reviewed_at=None,
            review_count=0,
            lapse_count=0,
            interval_index=0,
            interval_days=first,
            stability=None,
            difficulty=None,
            retrievability=None,
            target_retention=None,
            algorithm_version=EBBINGHAUS_ALGORITHM_VERSION,
            parameters=dict(params),
            last_calculation=calc,
            strategy_changed_at=now_utc,
        )

    stability = float(params["initial_stability_days"][GOOD])
    difficulty = float(params["initial_difficulty"])
    target = float(params["target_retention"])
    decay = float(params["decay"])
    interval = interval_for_retention(stability, target, decay)
    due = now_utc + timedelta(days=interval)
    calc = {
        "strategy": FSRS,
        "reason": (
            f"FSRS 初始化：以初始稳定性 {stability} 天、难度 {difficulty} 建模，"
            f"目标留存率 {target}，反解首次间隔 {interval:.6f} 天后复习。"
        ),
        "stability": stability,
        "difficulty": difficulty,
        "target_retention": target,
        "decay": decay,
        "factor": fsrs_factor(decay),
        "interval_days": interval,
        "due_at": _iso(due),
    }
    return ScheduleState(
        strategy=FSRS,
        due_at=due,
        last_reviewed_at=None,
        review_count=0,
        lapse_count=0,
        interval_index=0,
        interval_days=interval,
        stability=stability,
        difficulty=difficulty,
        retrievability=1.0,  # 刚学会时估计留存率
        target_retention=target,
        algorithm_version=FSRS_ALGORITHM_VERSION,
        parameters=dict(params),
        last_calculation=calc,
        strategy_changed_at=now_utc,
    )


def _memory_baseline(state: ScheduleState) -> datetime:
    """记忆起点：最后一次复习时间；从未复习时取学习 / 策略初始化时刻。"""
    return _to_utc(state.last_reviewed_at or state.strategy_changed_at)


# ---- 评分后计算（核心） ----
def review(
    state: ScheduleState,
    rating: str,
    reviewed_at: datetime,
    parameters: Mapping[str, Any] | None = None,
) -> ScheduleState:
    """给定当前状态与一次评分，返回全新状态（纯函数、确定、可复现）。

    ``parameters`` 为 None 时使用 ``state.parameters`` 历史快照，保证配置变化
    不会篡改历史计算结果。
    """
    validate_rating(rating)
    validate_strategy(state.strategy)
    at = _to_utc(reviewed_at)
    effective = _merge_parameters(state.strategy, parameters if parameters is not None else state.parameters)
    if state.strategy == EBBINGHAUS:
        return _review_ebbinghaus(state, rating, at, effective)
    return _review_fsrs(state, rating, at, effective)


def _review_ebbinghaus(
    state: ScheduleState,
    rating: str,
    at: datetime,
    params: dict[str, Any],
) -> ScheduleState:
    intervals = params["intervals_days"]
    last = len(intervals) - 1
    previous = max(0, state.interval_index)
    if rating == AGAIN:
        new_index, lapse_delta = 0, 1
    elif rating == HARD:
        new_index, lapse_delta = previous, 0
    elif rating == GOOD:
        new_index, lapse_delta = previous + 1, 0
    else:  # EASY
        new_index, lapse_delta = previous + 2, 0
    new_index = min(max(new_index, 0), last)
    interval_days = float(intervals[new_index])
    due = at + timedelta(days=interval_days)
    calc = {
        "strategy": EBBINGHAUS,
        "rating": rating,
        "previous_interval_index": previous,
        "interval_index": new_index,
        "intervals_days": list(intervals),
        "interval_days": interval_days,
        "due_at": _iso(due),
        "reason": (
            f"评分 {rating}：间隔档位 {previous} → {new_index}，"
            f"采用第 {new_index + 1} 档间隔 {interval_days} 天，下次到期 {_iso(due)}。"
            + ("（again 重置到首档）" if rating == AGAIN else "")
        ),
    }
    return replace(
        state,
        due_at=due,
        last_reviewed_at=at,
        review_count=state.review_count + 1,
        lapse_count=state.lapse_count + lapse_delta,
        interval_index=new_index,
        interval_days=interval_days,
        stability=None,
        difficulty=None,
        retrievability=None,
        target_retention=None,
        algorithm_version=EBBINGHAUS_ALGORITHM_VERSION,
        parameters=dict(params),
        last_calculation=calc,
    )


def _review_fsrs(
    state: ScheduleState,
    rating: str,
    at: datetime,
    params: dict[str, Any],
) -> ScheduleState:
    decay = float(params["decay"])
    target = float(params["target_retention"])
    min_s = float(params["min_stability_days"])
    s_before = float(state.stability) if state.stability is not None else float(params["initial_stability_days"][rating])
    d_before = float(state.difficulty) if state.difficulty is not None else float(params["initial_difficulty"])
    elapsed = _elapsed_days(_memory_baseline(state), at)
    r_before = retrievability_curve(s_before, elapsed, decay)
    grade = RATING_TO_INT[rating]
    lapse_count = state.lapse_count

    if rating == AGAIN:
        s_after = min(s_before, max(min_s, s_before * float(params["lapse_stability_multiplier"])))
        d_after = _clamp(d_before + float(params["lapse_difficulty_delta"]), 1.0, 10.0)
        lapse_count += 1
        branch = "lapse"
        stability_multiplier = 1.0
    else:
        penalty = (
            float(params["hard_penalty"]) if rating == HARD
            else float(params["easy_bonus"]) if rating == EASY
            else 1.0
        )
        gain = math.exp(float(params["stability_gain"]))
        s_inc = 1.0 + (
            gain
            * (11.0 - d_before)
            * (s_before ** (-float(params["stability_exponent"])))
            * (math.exp((1.0 - r_before) * float(params["retrievability_gain"])) - 1.0)
            * penalty
        )
        s_inc = max(s_inc, 1.0)  # 成功回忆至少不降低稳定性
        s_after = max(min_s, s_before * s_inc)
        stability_multiplier = s_inc
        d_linear = d_before - float(params["difficulty_delta"]) * (grade - 3)
        mr = float(params["mean_reversion"])
        d_after = _clamp(mr * float(params["initial_difficulty"]) + (1.0 - mr) * d_linear, 1.0, 10.0)
        branch = "success"

    interval = interval_for_retention(s_after, target, decay)
    due = at + timedelta(days=interval)
    calc = {
        "strategy": FSRS,
        "branch": branch,
        "rating": rating,
        "grade": grade,
        "reviewed_at": _iso(at),
        "memory_baseline": _iso(_memory_baseline(state)),
        "elapsed_days": elapsed,
        "retrievability_before": r_before,
        "stability_before": s_before,
        "stability_after": s_after,
        "stability_multiplier": stability_multiplier,
        "difficulty_before": d_before,
        "difficulty_after": d_after,
        "target_retention": target,
        "decay": decay,
        "factor": fsrs_factor(decay),
        "interval_days": interval,
        "due_at": _iso(due),
        "reason": (
            f"FSRS 评分 {rating}（{branch}）：复习前估计留存率 {r_before:.4f}，"
            f"稳定性 {s_before:.4f} → {s_after:.4f} 天，难度 {d_before:.4f} → {d_after:.4f}；"
            f"按目标留存率 {target} 反解间隔 {interval:.4f} 天，下次到期 {_iso(due)}。"
        ),
    }
    return replace(
        state,
        due_at=due,
        last_reviewed_at=at,
        review_count=state.review_count + 1,
        lapse_count=lapse_count,
        interval_days=interval,
        stability=s_after,
        difficulty=d_after,
        retrievability=r_before,  # 本次复习前估计留存率（"为什么今天复习"依据）
        target_retention=target,
        algorithm_version=FSRS_ALGORITHM_VERSION,
        parameters=dict(params),
        last_calculation=calc,
    )


# ---- 可提取性 / 可解释性 ----
def retrievability_at(
    state: ScheduleState,
    at: datetime,
    parameters: Mapping[str, Any] | None = None,
) -> float | None:
    """返回 ``at`` 时刻的估计可提取性；固定间隔策略不建模连续留存率，返回 None。"""
    if state.strategy != FSRS:
        return None
    params = _merge_parameters(FSRS, parameters if parameters is not None else state.parameters)
    s = float(state.stability) if state.stability is not None else 0.0
    elapsed = _elapsed_days(_memory_baseline(state), _to_utc(at))
    return retrievability_curve(s, elapsed, float(params["decay"]))


def explain(
    state: ScheduleState,
    at: datetime,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """"为什么今天复习我"：结构化、中文可读、可复现的计算依据。"""
    at_utc = _to_utc(at)
    due = _to_utc(state.due_at)
    days_overdue = max((at_utc - due).total_seconds() / SECONDS_PER_DAY, 0.0)
    is_due = at_utc >= due
    r_now = retrievability_at(state, at_utc, parameters)

    if state.strategy == FSRS:
        stability = state.stability
        difficulty = state.difficulty
        target = state.target_retention
        tail = (
            f"当前({_iso(at_utc)})估计可提取性 {r_now:.4f}"
            + (f"，已(将)接近目标留存率 {target}" if r_now is not None and target is not None and r_now <= target else "")
            + "，因此触发复习。"
            if is_due
            else "，尚未到复习时间。"
        )
        reason = (
            f"FSRS 自适应调度：记忆稳定性 {stability} 天、难度 {difficulty}，"
            f"目标留存率 {target}；到期时间 {_iso(due)}，已逾期 {days_overdue:.2f} 天。{tail}"
        )
    else:
        reason = (
            f"艾宾浩斯固定间隔：第 {state.interval_index + 1} 档，间隔 {state.interval_days} 天；"
            f"到期时间 {_iso(due)}，已逾期 {days_overdue:.2f} 天，"
            + ("今日应复习。" if is_due else "尚未到期。")
        )

    return {
        "strategy": state.strategy,
        "at": _iso(at_utc),
        "due_at": _iso(due),
        "is_due": is_due,
        "days_overdue_days": round(days_overdue, 6),
        "retrievability": r_now,
        "target_retention": state.target_retention,
        "stability": state.stability,
        "difficulty": state.difficulty,
        "review_count": state.review_count,
        "lapse_count": state.lapse_count,
        "interval_index": state.interval_index,
        "interval_days": state.interval_days,
        "algorithm_version": state.algorithm_version,
        "parameters": dict(state.parameters),
        "last_calculation": dict(state.last_calculation),
        "reason": reason,
        # 复现输入快照：把 (state, at, parameters) 三者固定即可完全复算
        "inputs": {
            "state": to_dict(state),
            "at": _iso(at_utc),
        },
    }


# ---- 策略切换与对照 ----
def switch_strategy(
    state: ScheduleState,
    new_strategy: str,
    now: datetime,
    parameters: Mapping[str, Any] | None = None,
) -> ScheduleState:
    """切换策略：用当前记忆状态初始化目标策略，保留历史计数，不改历史记录。

    相同策略视为 no-op；切换时间写入 ``strategy_changed_at``。
    """
    validate_strategy(new_strategy)
    now_utc = _to_utc(now)
    if new_strategy == state.strategy:
        return state

    if new_strategy == EBBINGHAUS:
        params = _merge_parameters(EBBINGHAUS, parameters)
        intervals = params["intervals_days"]
        index = min(max(state.review_count - state.lapse_count, 0), len(intervals) - 1)
        interval_days = float(intervals[index])
        due = now_utc + timedelta(days=interval_days)
        calc = {
            "strategy": EBBINGHAUS,
            "reason": (
                f"从 {state.strategy} 切换到艾宾浩斯：以历史成功复习次数 "
                f"{state.review_count - state.lapse_count} 映射到第 {index + 1} 档间隔 "
                f"{interval_days} 天；历史计数保持不变。"
            ),
            "source_strategy": state.strategy,
            "source_stability": state.stability,
            "source_difficulty": state.difficulty,
            "mapped_from_review_count": state.review_count,
            "interval_index": index,
            "interval_days": interval_days,
            "due_at": _iso(due),
        }
        return replace(
            state,
            strategy=EBBINGHAUS,
            due_at=due,
            last_reviewed_at=now_utc,
            interval_index=index,
            interval_days=interval_days,
            stability=None,
            difficulty=None,
            retrievability=None,
            target_retention=None,
            algorithm_version=EBBINGHAUS_ALGORITHM_VERSION,
            parameters=dict(params),
            last_calculation=calc,
            strategy_changed_at=now_utc,
        )

    params = _merge_parameters(FSRS, parameters)
    s = state.stability
    if s is None:
        s = state.interval_days if state.interval_days is not None else params["initial_stability_days"][GOOD]
    s = max(float(params["min_stability_days"]), float(s))
    d = float(state.difficulty) if state.difficulty is not None else float(params["initial_difficulty"])
    target = float(params["target_retention"])
    decay = float(params["decay"])
    interval = interval_for_retention(s, target, decay)
    due = now_utc + timedelta(days=interval)
    calc = {
        "strategy": FSRS,
        "reason": (
            f"从 {state.strategy} 切换到 FSRS：以当前记忆状态初始化，"
            f"稳定性 {s} 天、难度 {d}，目标留存率 {target}，反解间隔 {interval:.6f} 天；"
            "历史计数保持不变。"
        ),
        "source_strategy": state.strategy,
        "source_interval_days": state.interval_days,
        "stability": s,
        "difficulty": d,
        "target_retention": target,
        "interval_days": interval,
        "due_at": _iso(due),
    }
    return replace(
        state,
        strategy=FSRS,
        due_at=due,
        last_reviewed_at=now_utc,
        interval_days=interval,
        stability=s,
        difficulty=d,
        retrievability=1.0,
        target_retention=target,
        algorithm_version=FSRS_ALGORITHM_VERSION,
        parameters=dict(params),
        last_calculation=calc,
        strategy_changed_at=now_utc,
    )


def project_review(
    state: ScheduleState,
    strategy: str,
    rating: str,
    reviewed_at: datetime,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """以同一状态为基准，投影到指定策略下一次评分后的结果（不写库）。"""
    validate_strategy(strategy)
    base = state if state.strategy == strategy else switch_strategy(state, strategy, reviewed_at, parameters)
    projected = review(base, rating, reviewed_at)
    return {
        "due_at": _iso(projected.due_at),
        "state": to_dict(projected),
        "explanation": explain(projected, reviewed_at),
    }


def compare(
    state: ScheduleState,
    rating: str,
    reviewed_at: datetime,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """两套策略对照：以同一状态纯计算两种结果，对应 ScheduleCompareResponse。"""
    validate_rating(rating)
    at = _to_utc(reviewed_at)
    return {
        "ebbinghaus": project_review(state, EBBINGHAUS, rating, at, parameters),
        "fsrs": project_review(state, FSRS, rating, at, parameters),
    }


__all__ = [
    "EBBINGHAUS", "FSRS", "SUPPORTED_STRATEGIES",
    "AGAIN", "HARD", "GOOD", "EASY", "RATING_VALUES", "RATING_TO_INT",
    "EBBINGHAUS_ALGORITHM_VERSION", "FSRS_ALGORITHM_VERSION",
    "default_ebbinghaus_parameters", "default_fsrs_parameters", "default_parameters",
    "validate_strategy", "validate_rating",
    "fsrs_factor", "retrievability_curve", "interval_for_retention",
    "ScheduleState", "to_dict", "from_mapping",
    "initial_state", "review", "retrievability_at", "explain",
    "switch_strategy", "project_review", "compare",
]
