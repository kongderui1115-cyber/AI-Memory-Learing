"""调度与每日任务生成的真实单元测试（Python 标准库 unittest，无 pytest / mock）。

覆盖：艾宾浩斯固定间隔序列、again/hard/easy 规则、FSRS 遗忘曲线常数与评分序列、
策略切换、双策略对照、可解释输出、幂等重放、漏复习滚动、配置缺失明确报错。

运行（worktree 根目录）：
    python -m unittest discover -s backend/tests_backend -v
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# unittest discover 的 top_level_dir 是 start_dir，需要手动把 backend/ 加入导入路径。
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import config  # noqa: E402
from app.domain import daily_tasks as dt  # noqa: E402
from app.domain import scheduling as sched  # noqa: E402

BASE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
DAY = date(2026, 1, 10)
AS_OF = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
VALID_ENV = {
    "DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:5432/memos",
    "SECRET_KEY": "a-real-secret-key-value-with-32-characters",
}


def candidate(
    kp: str,
    due: datetime,
    subject: str | None = "math",
    difficulty: int = 3,
    lapse: int = 0,
    hint: int = 0,
) -> dt.DueCandidate:
    return dt.DueCandidate(
        knowledge_point_id=kp,
        due_at=due,
        subject_id=subject,
        difficulty=difficulty,
        lapse_count=lapse,
        priority_hint=hint,
    )


class EbbinghausTests(unittest.TestCase):
    """BE-05：艾宾浩斯固定间隔固定用例。"""

    def test_initial_state(self):
        s = sched.initial_state(sched.EBBINGHAUS, BASE)
        self.assertEqual(s.strategy, "ebbinghaus")
        self.assertEqual(s.interval_index, 0)
        self.assertEqual(s.interval_days, 1)
        self.assertEqual(s.due_at, BASE + timedelta(days=1))
        self.assertEqual(s.review_count, 0)
        self.assertIsNone(s.stability)
        self.assertEqual(s.algorithm_version, "ebbinghaus-fixed-1")
        self.assertIn("固定间隔", s.last_calculation["reason"])

    def test_good_advances_fixed_interval_sequence(self):
        intervals = [1, 2, 4, 7, 15, 30]
        s = sched.initial_state(sched.EBBINGHAUS, BASE)
        at = s.due_at
        for i in range(8):
            s = sched.review(s, sched.GOOD, at)
            expected_index = min(i + 1, len(intervals) - 1)
            expected_interval = intervals[expected_index]
            self.assertEqual(s.interval_index, expected_index)
            self.assertEqual(s.interval_days, expected_interval)
            self.assertEqual(s.due_at, at + timedelta(days=expected_interval))
            at = s.due_at
        # 超出序列沿用末项
        self.assertEqual(s.interval_days, 30)
        self.assertEqual(s.review_count, 8)

    def test_again_hard_easy_rules(self):
        s = sched.initial_state(sched.EBBINGHAUS, BASE)
        for _ in range(3):
            s = sched.review(s, sched.GOOD, s.due_at)
        self.assertEqual(s.interval_index, 3)
        reviewed_at = s.due_at

        again = sched.review(s, sched.AGAIN, reviewed_at)
        self.assertEqual(again.interval_index, 0)
        self.assertEqual(again.interval_days, 1)
        self.assertEqual(again.lapse_count, 1)
        self.assertEqual(again.due_at, reviewed_at + timedelta(days=1))
        self.assertEqual(again.review_count, 4)

        hard = sched.review(s, sched.HARD, reviewed_at)
        self.assertEqual(hard.interval_index, 3)  # 停留
        self.assertEqual(hard.lapse_count, 0)

        easy = sched.review(s, sched.EASY, reviewed_at)
        self.assertEqual(easy.interval_index, 5)  # +2 -> 末档
        self.assertEqual(easy.interval_days, 30)

    def test_custom_intervals_and_explain(self):
        s = sched.initial_state(sched.EBBINGHAUS, BASE, {"intervals_days": [2, 5, 9]})
        self.assertEqual(s.interval_days, 2)
        s = sched.review(s, sched.GOOD, s.due_at)
        self.assertEqual(s.interval_days, 5)
        exp = sched.explain(s, s.due_at + timedelta(days=1))
        self.assertTrue(exp["is_due"])
        self.assertEqual(exp["days_overdue_days"], 1.0)
        self.assertIsNone(exp["retrievability"])
        self.assertIn("固定间隔", exp["reason"])
        json.dumps(exp)  # 可 JSON 序列化


class FsrsTests(unittest.TestCase):
    """BE-05：FSRS 遗忘曲线常数、评分序列、确定性与可复现。"""

    def test_curve_constants(self):
        self.assertAlmostEqual(sched.fsrs_factor(-0.5), 1.0 / 0.81 - 1.0, places=12)
        # R(t=S)=0.9；I(S, 0.9)=S（由 FACTOR 定义保证）
        self.assertAlmostEqual(sched.retrievability_curve(10.0, 10.0, -0.5), 0.9, places=10)
        self.assertAlmostEqual(sched.interval_for_retention(10.0, 0.9, -0.5), 10.0, places=10)
        self.assertEqual(sched.retrievability_curve(5.0, 0.0, -0.5), 1.0)
        self.assertLess(sched.retrievability_curve(5.0, 20.0, -0.5), 0.9)
        # 目标留存率越低，允许间隔越长
        self.assertGreater(
            sched.interval_for_retention(10.0, 0.8, -0.5),
            sched.interval_for_retention(10.0, 0.9, -0.5),
        )

    def test_initial_state(self):
        s = sched.initial_state(sched.FSRS, BASE)
        self.assertEqual(s.strategy, "fsrs")
        self.assertEqual(s.stability, 3.5)
        self.assertEqual(s.difficulty, 5.0)
        self.assertEqual(s.target_retention, 0.9)
        self.assertEqual(s.retrievability, 1.0)
        self.assertAlmostEqual(s.interval_days, 3.5, places=10)
        self.assertAlmostEqual((s.due_at - BASE).total_seconds(), 3.5 * 86400, places=3)
        self.assertEqual(s.algorithm_version, "fsrs-parametric-1")

    def test_good_sequence_and_again_lapse(self):
        s = sched.initial_state(sched.FSRS, BASE)
        s1 = sched.review(s, sched.GOOD, s.due_at)
        self.assertGreater(s1.stability, s.stability)
        self.assertGreater(s1.interval_days, s.interval_days)
        self.assertGreater(s1.due_at, s.due_at)
        self.assertEqual(s1.review_count, 1)
        self.assertLess(s1.retrievability, 1.0)  # 复习前估计留存率 ~0.9
        self.assertEqual(s1.last_calculation["branch"], "success")

        s2 = sched.review(s1, sched.GOOD, s1.due_at)
        self.assertGreater(s2.stability, s1.stability)

        again = sched.review(s1, sched.AGAIN, s1.due_at)
        self.assertLess(again.stability, s1.stability)
        self.assertLess(again.due_at, s2.due_at)  # again 的下次到期早于 good
        self.assertEqual(again.lapse_count, 1)
        self.assertEqual(again.last_calculation["branch"], "lapse")

    def test_rating_order_hard_good_easy(self):
        base = sched.initial_state(sched.FSRS, BASE)
        at = base.due_at
        hard = sched.review(base, sched.HARD, at)
        good = sched.review(base, sched.GOOD, at)
        easy = sched.review(base, sched.EASY, at)
        self.assertLess(hard.stability, good.stability)
        self.assertLess(good.stability, easy.stability)
        self.assertLess(hard.interval_days, good.interval_days)
        self.assertLess(good.interval_days, easy.interval_days)
        self.assertLess(hard.due_at, good.due_at)
        self.assertLess(good.due_at, easy.due_at)

    def test_deterministic_and_reproducible(self):
        s = sched.initial_state(sched.FSRS, BASE)
        a = sched.review(s, sched.GOOD, s.due_at)
        b = sched.review(s, sched.GOOD, s.due_at)
        self.assertEqual(a, b)
        self.assertEqual(sched.to_dict(a), sched.to_dict(b))
        restored = sched.from_mapping(sched.to_dict(a))
        self.assertEqual(sched.to_dict(a), sched.to_dict(restored))
        self.assertEqual(s.review_count, 0)  # 纯函数不改原状态
        # 参数快照沿用：修改全局默认不影响已构造状态的历史计算
        c = sched.review(a, sched.GOOD, a.due_at)
        self.assertEqual(c.parameters["target_retention"], 0.9)
        self.assertIn("stability_after", c.last_calculation)
        json.dumps(sched.to_dict(c))

    def test_explain_why_today(self):
        s = sched.initial_state(sched.FSRS, BASE)
        exp = sched.explain(s, s.due_at)
        self.assertTrue(exp["is_due"])
        self.assertAlmostEqual(exp["retrievability"], 0.9, places=4)
        self.assertEqual(exp["inputs"]["state"]["strategy"], "fsrs")
        self.assertIn("FSRS", exp["reason"])
        json.dumps(exp)


class StrategySwitchAndCompareTests(unittest.TestCase):
    """BE-05：策略切换与双策略对照。"""

    def test_switch_both_directions_preserves_history(self):
        e = sched.initial_state(sched.EBBINGHAUS, BASE)
        e = sched.review(e, sched.GOOD, e.due_at)
        e = sched.review(e, sched.GOOD, e.due_at)
        switch_time = BASE + timedelta(days=10)
        f = sched.switch_strategy(e, sched.FSRS, switch_time)
        self.assertEqual(f.strategy, "fsrs")
        self.assertEqual(f.review_count, 2)
        self.assertEqual(f.strategy_changed_at, switch_time)
        self.assertIsNotNone(f.stability)
        self.assertEqual(f.target_retention, 0.9)
        self.assertIn("切换", f.last_calculation["reason"])

        back = sched.switch_strategy(f, sched.EBBINGHAUS, switch_time + timedelta(days=1))
        self.assertEqual(back.strategy, "ebbinghaus")
        self.assertEqual(back.review_count, 2)
        self.assertIsNone(back.stability)
        self.assertIs(f, sched.switch_strategy(f, sched.FSRS, switch_time))  # no-op

    def test_compare_is_pure_and_serializable(self):
        s = sched.initial_state(sched.FSRS, BASE)
        result = sched.compare(s, sched.GOOD, s.due_at)
        self.assertEqual(set(result), {"ebbinghaus", "fsrs"})
        for name, projection in result.items():
            self.assertIn("due_at", projection)
            self.assertIn("state", projection)
            self.assertIn("explanation", projection)
            self.assertEqual(projection["state"]["strategy"], name)
        self.assertEqual(s.review_count, 0)  # 不写库 / 不改原状态
        json.dumps(result)

    def test_invalid_inputs_raise(self):
        s = sched.initial_state(sched.FSRS, BASE)
        with self.assertRaises(ValueError):
            sched.review(s, "unknown", s.due_at)
        with self.assertRaises(ValueError):
            sched.initial_state("sm2", BASE)
        with self.assertRaises(ValueError):
            sched.review(s, sched.GOOD, datetime(2026, 1, 1))  # naive datetime
        with self.assertRaises(ValueError):
            sched.validate_rating("x")
        with self.assertRaises(ValueError):
            sched.default_parameters("x")


class DailyTaskTests(unittest.TestCase):
    """BE-06：到期筛选、优先级、上限、幂等、补漏滚动。"""

    def test_select_due_and_subject_filter(self):
        items = [
            candidate("kp-overdue", AS_OF - timedelta(days=3)),
            candidate("kp-today", AS_OF),
            candidate("kp-future", AS_OF + timedelta(days=1)),
            candidate("kp-other", AS_OF, subject="english"),
        ]
        self.assertEqual(
            {c.knowledge_point_id for c in dt.select_due(items, AS_OF)},
            {"kp-overdue", "kp-today", "kp-other"},
        )
        self.assertEqual(
            {c.knowledge_point_id for c in dt.select_due(items, AS_OF, subject_id="math")},
            {"kp-overdue", "kp-today"},
        )

    def test_ranking_and_daily_limit(self):
        items = [
            candidate("kp-a", AS_OF - timedelta(days=1)),
            candidate("kp-b", AS_OF - timedelta(days=5)),
            candidate("kp-c", AS_OF),
        ]
        ranked = dt.rank_candidates(items, AS_OF)
        self.assertEqual([c.knowledge_point_id for c in ranked], ["kp-b", "kp-a", "kp-c"])
        plan = dt.generate_daily_batch(
            user_id="u1", local_date=DAY, timezone_name="Asia/Shanghai",
            as_of=AS_OF, candidates=items, daily_limit=2,
        )
        self.assertEqual(len(plan.tasks), 2)
        self.assertEqual(plan.tasks[0].knowledge_point_id, "kp-b")
        self.assertGreaterEqual(plan.tasks[0].priority, plan.tasks[1].priority)
        self.assertEqual([t.position for t in plan.tasks], [1, 2])
        self.assertEqual(plan.status, "ready")

    def test_generation_is_deterministic(self):
        items = [candidate("kp-a", AS_OF - timedelta(days=1)), candidate("kp-b", AS_OF)]
        kwargs = dict(user_id="u1", local_date=DAY, timezone_name="Asia/Shanghai", as_of=AS_OF, candidates=items)
        p1 = dt.generate_daily_batch(**kwargs)
        p2 = dt.generate_daily_batch(**kwargs)
        self.assertEqual(p1, p2)
        self.assertEqual(p1.idempotency_key, p2.idempotency_key)
        self.assertTrue(p1.idempotency_key.startswith("u1:2026-01-10:all:"))
        json.dumps(p1.to_dict())

    def test_idempotent_replay_and_existing_ids(self):
        items = [candidate("kp-a", AS_OF - timedelta(days=1)), candidate("kp-b", AS_OF)]
        kwargs = dict(user_id="u1", local_date=DAY, timezone_name="Asia/Shanghai", as_of=AS_OF, candidates=items)
        p1 = dt.generate_daily_batch(**kwargs)
        replay = dt.generate_daily_batch(**kwargs, existing_plan=p1)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.tasks, p1.tasks)
        self.assertEqual(replay.idempotency_key, p1.idempotency_key)

        # 已有任务的知识点不重复生成
        skipped = dt.generate_daily_batch(**kwargs, existing_task_knowledge_point_ids=p1.knowledge_point_ids())
        self.assertEqual(skipped.tasks, ())
        # 不同日期 -> 不同幂等键（新批次，逾期项滚入）
        p_next = dt.generate_daily_batch(**{**kwargs, "local_date": date(2026, 1, 11)})
        self.assertNotEqual(p_next.idempotency_key, p1.idempotency_key)

    def test_overdue_rolls_in_without_losing_due(self):
        original_due = AS_OF - timedelta(days=3)
        plan = dt.generate_daily_batch(
            user_id="u1", local_date=DAY, timezone_name="Asia/Shanghai",
            as_of=AS_OF, candidates=[candidate("kp-overdue", original_due)],
        )
        task = plan.tasks[0]
        self.assertEqual(task.knowledge_point_id, "kp-overdue")
        self.assertEqual(task.scheduled_due_at, original_due)  # due 不丢失、不刷新
        self.assertFalse(task.carried_over)

    def test_carry_over_unfinished_tasks(self):
        original_due = AS_OF - timedelta(days=2)
        previous = dt.DailyTaskPlan(
            knowledge_point_id="kp-pending",
            review_item_id=None,
            scheduled_due_at=original_due,
            priority=200,
            position=1,
            status="pending",
            subject_id="math",
            difficulty=4,
            lapse_count=2,
        )
        pending = dt.unfinished_tasks([previous, dt.DailyTaskPlan(
            knowledge_point_id="kp-done", review_item_id=None, scheduled_due_at=original_due,
            priority=1, position=2, status="completed",
        )])
        self.assertEqual([t.knowledge_point_id for t in pending], ["kp-pending"])

        next_day = AS_OF + timedelta(days=1)
        plan = dt.generate_daily_batch(
            user_id="u1", local_date=date(2026, 1, 11), timezone_name="Asia/Shanghai",
            as_of=next_day, candidates=[], carry_over=pending,
        )
        self.assertEqual(len(plan.tasks), 1)
        rolled = plan.tasks[0]
        self.assertEqual(rolled.knowledge_point_id, "kp-pending")
        self.assertTrue(rolled.carried_over)
        self.assertEqual(rolled.scheduled_due_at, original_due)  # 保留原 due

    def test_daily_limit_and_time_validation(self):
        kwargs = dict(user_id="u1", local_date=DAY, timezone_name="Asia/Shanghai",
                      as_of=AS_OF, candidates=[candidate("kp-a", AS_OF)])
        with self.assertRaises(ValueError):
            dt.generate_daily_batch(**kwargs, daily_limit=0)
        with self.assertRaises(ValueError):
            dt.generate_daily_batch(**kwargs, daily_limit=501)
        with self.assertRaises(ValueError):
            dt.generate_daily_batch(**{**kwargs, "as_of": datetime(2026, 1, 10)})  # naive


class ConfigTests(unittest.TestCase):
    """BE-01：配置读取，缺失必需项 / 占位符 / 非 PostgreSQL 明确报错。"""

    def test_missing_required_raises(self):
        with self.assertRaises(config.ConfigMissingError) as ctx:
            config.load_settings(env={})
        self.assertEqual(set(ctx.exception.missing), {"DATABASE_URL", "SECRET_KEY"})
        self.assertEqual(config.ConfigMissingError.code, "CONFIG_MISSING")

    def test_placeholders_rejected(self):
        with self.assertRaises(config.ConfigMissingError) as ctx:
            config.load_settings(env={
                "DATABASE_URL": "postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME",
                "SECRET_KEY": "REPLACE_ME",
            })
        self.assertEqual(set(ctx.exception.missing), {"DATABASE_URL", "SECRET_KEY"})

    def test_valid_settings(self):
        s = config.load_settings(env={
            **VALID_ENV,
            "APP_PORT": "9000",
            "EBBINGHAUS_INTERVALS_DAYS": "1,3,7",
            "FSRS_TARGET_RETENTION": "0.85",
            "DAILY_REVIEW_LIMIT": "50",
            "AI_BILLING_APPROVED": "true",
        })
        self.assertEqual(s.app_port, 9000)
        self.assertEqual(s.ebbinghaus_intervals_days, (1, 3, 7))
        self.assertAlmostEqual(s.fsrs_target_retention, 0.85)
        self.assertEqual(s.daily_review_limit, 50)
        self.assertTrue(s.ai_billing_approved)
        self.assertEqual(config.assert_database_configured(s), s.database_url)

    def test_sqlite_is_rejected(self):
        s = config.Settings(database_url="sqlite:///local.db")
        with self.assertRaises(config.ConfigMissingError):
            config.assert_database_configured(s)

    def test_credentials_and_billing_are_explicit(self):
        s = config.load_settings(env=VALID_ENV)
        with self.assertRaises(config.ConfigMissingError):
            s.require("AI_API_KEY")
        with self.assertRaises(config.ConfigMissingError):
            config.require_ai_billing(s)
        s2 = config.load_settings(env={**VALID_ENV, "NOTION_API_TOKEN": "secret-token"})
        self.assertEqual(s2.require("NOTION_API_TOKEN"), "secret-token")


if __name__ == "__main__":
    unittest.main(verbosity=2)
