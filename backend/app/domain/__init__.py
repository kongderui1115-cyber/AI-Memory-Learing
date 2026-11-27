"""领域层：纯函数与实体规则，不依赖任何框架 / 数据库 / 第三方库。

- :mod:`app.domain.scheduling` —— BE-05 艾宾浩斯固定间隔 + FSRS 自适应调度；
- :mod:`app.domain.daily_tasks` —— BE-06 每日复习任务生成（筛选 / 优先级 / 上限 / 幂等 / 补漏）。
"""
from . import daily_tasks, scheduling
from .daily_tasks import *  # noqa: F401,F403
from .scheduling import *  # noqa: F401,F403

__all__ = (
    ["daily_tasks", "scheduling"]
    + list(scheduling.__all__)
    + list(daily_tasks.__all__)
)
