"""AIExecutionService 编排与「缺 Key 报错」硬约束路径测试。

说明（质量红线）：
- 缺 Key / 未授权计费 / 不发起 HTTP / 重试与限流判定均为**真实逻辑**；
- 成功与重试用例使用 **MOCK** ``FakeTransport`` 仅隔离外部 HTTP
  （DeepSeek / OpenAI 一律未真实调用、不联网、不产生费用），
  **不代表外部服务联调通过**；真实联调为 AI-07（待 BLK-02 授权）。
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _support  # noqa: E402  提供明确标注的 HTTP MOCK
from app.ai.config import load_provider_config  # noqa: E402
from app.ai.errors import (  # noqa: E402
    BillingNotApprovedError,
    ConfigMissingError,
    ProviderAuthError,
    ProviderRateLimitedError,
    ProviderServiceError,
)
from app.ai.ports import StructuredRequest  # noqa: E402
from app.ai.service import AIExecutionService  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _request(operation="extract_knowledge"):
    return StructuredRequest(
        operation=operation,
        prompt_version="kp-extract-v1",
        system="只输出 JSON",
        user="笔记内容",
    )


def _config(**overrides):
    env = {"AI_PROVIDER": "deepseek", "AI_MODEL": "deepseek-chat"}
    env.update(overrides)
    return load_provider_config(env)


def _ready_env(**overrides):
    env = {"AI_API_KEY": "sk-test", "AI_BILLING_APPROVED": "true"}
    env.update(overrides)
    return env


class MissingCredentialHardConstraintTests(unittest.TestCase):
    """硬约束：缺 Key 或未授权计费时绝不发起 HTTP、绝不返回伪造结果。"""

    def test_missing_key_raises_and_no_http_call(self):
        fake = _support.FakeTransport([_support.ai_success_response({"ok": True})])
        service = AIExecutionService(
            env={"AI_BILLING_APPROVED": "true"}, transport=fake,
            sleeper=lambda _: None,
        )
        with self.assertRaises(ConfigMissingError) as ctx:
            service.complete(_config(), _request())
        self.assertEqual(ctx.exception.code, "CONFIG_MISSING")
        self.assertEqual(fake.calls, [])  # 一次 HTTP 都没有发起
        self.assertIn("AI_API_KEY", ctx.exception.message)

    def test_billing_not_approved_raises_and_no_http_call(self):
        fake = _support.FakeTransport([_support.ai_success_response({"ok": True})])
        service = AIExecutionService(
            env={"AI_API_KEY": "sk-test", "AI_BILLING_APPROVED": "false"},
            transport=fake, sleeper=lambda _: None,
        )
        with self.assertRaises(BillingNotApprovedError):
            service.complete(_config(), _request())
        self.assertEqual(fake.calls, [])

    def test_no_env_at_all_raises(self):
        service = AIExecutionService(env={}, transport=_support.FakeTransport(),
                                     sleeper=lambda _: None)
        with self.assertRaises(ConfigMissingError):
            service.complete(_config(), _request())


class ExecutionTests(unittest.TestCase):
    """以下用例的 HTTP 传输为 MOCK（FakeTransport），仅隔离外部调用。"""

    def test_success_records_succeeded_call_log(self):
        fake = _support.FakeTransport(
            [_support.ai_success_response({"knowledge_points": [{"title": "T"}]},
                                          input_tokens=10, output_tokens=6)]
        )
        service = AIExecutionService(
            env=_ready_env(), transport=fake, sleeper=lambda _: None,
            clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        completed = service.complete(_config(), _request())
        self.assertEqual(completed.result.parsed["knowledge_points"][0]["title"], "T")
        log = completed.call_log
        self.assertEqual(log.status, "succeeded")
        self.assertEqual(log.attempt_count, 1)
        self.assertEqual(log.total_tokens, 16)
        self.assertEqual(log.provider, "deepseek")
        self.assertEqual(log.operation, "extract_knowledge")
        self.assertEqual(len(fake.calls), 1)

    def test_retry_on_503_then_success(self):
        sleeps: list[float] = []
        fake = _support.FakeTransport(
            [
                _support.http_error_response(503),
                _support.ai_success_response({"items": []}),
            ]
        )
        service = AIExecutionService(
            env=_ready_env(), transport=fake, sleeper=sleeps.append,
            clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        completed = service.complete(_config(AI_MAX_RETRIES="3"), _request())
        self.assertEqual(completed.call_log.status, "succeeded")
        self.assertEqual(completed.call_log.attempt_count, 2)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(sleeps, [1.0])

    def test_auth_error_is_not_retried(self):
        fake = _support.FakeTransport([_support.http_error_response(401)])
        service = AIExecutionService(
            env=_ready_env(), transport=fake, sleeper=lambda _: None,
        )
        with self.assertRaises(ProviderAuthError):
            service.complete(_config(AI_MAX_RETRIES="3"), _request())
        self.assertEqual(len(fake.calls), 1)

    def test_retries_exhausted_records_failed_log(self):
        sleeps: list[float] = []
        fake = _support.FakeTransport(
            [_support.http_error_response(500), _support.http_error_response(500)]
        )
        service = AIExecutionService(
            env=_ready_env(), transport=fake, sleeper=sleeps.append,
        )
        with self.assertRaises(ProviderServiceError):
            service.complete(_config(AI_MAX_RETRIES="1"), _request())
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(sleeps, [1.0])

    def test_rate_limit_returns_429_without_second_http_call(self):
        fake = _support.FakeTransport(
            [
                _support.ai_success_response({"a": 1}),
                _support.ai_success_response({"a": 2}),
            ]
        )
        service = AIExecutionService(
            env=_ready_env(), transport=fake, sleeper=lambda _: None,
            limiter_clock=FakeClock(),
        )
        config = _config(AI_RATE_LIMIT_PER_MINUTE="1")
        service.complete(config, _request("extract_knowledge"))
        with self.assertRaises(ProviderRateLimitedError) as ctx:
            service.complete(config, _request("generate_review_items"))
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")
        self.assertEqual(len(fake.calls), 1)  # 第二次被限流，未发请求


if __name__ == "__main__":
    unittest.main()
