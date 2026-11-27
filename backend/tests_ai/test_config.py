"""AI-01 配置读取与「缺 Key / 未授权计费」硬约束测试。

全部为真实纯逻辑测试：不使用任何 mock、不联网、不读取真实环境变量
（env 全部显式注入 dict）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.ai.config import (  # noqa: E402
    AIProviderConfig,
    assert_ready,
    billing_approved,
    collect_readiness_problems,
    ensure_billing_approved,
    load_provider_config,
    with_model,
)
from app.ai.errors import (  # noqa: E402
    BillingNotApprovedError,
    ConfigMissingError,
    StructuredOutputError,
)


class LoadConfigTests(unittest.TestCase):
    def test_load_defaults(self):
        config = load_provider_config({})
        self.assertEqual(config.provider, "deepseek")
        self.assertEqual(config.model_name, "deepseek-chat")
        self.assertEqual(config.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(config.credential_ref, "AI_API_KEY")
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.timeout_seconds, 60)
        self.assertEqual(config.max_retries, 3)
        self.assertIsNone(config.rate_limit_per_minute)
        self.assertTrue(config.is_enabled)

    def test_load_custom_values(self):
        config = load_provider_config(
            {
                "AI_PROVIDER": "openai",
                "AI_MODEL": "gpt-4o",
                "AI_BASE_URL": "https://proxy.example/v1",
                "AI_TEMPERATURE": "0.7",
                "AI_TIMEOUT_SECONDS": "15",
                "AI_MAX_RETRIES": "5",
                "AI_RATE_LIMIT_PER_MINUTE": "20",
                "AI_API_KEY_REF": "MY_SECRET",
                "AI_BILLING_APPROVED": "true",
            }
        )
        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.model_name, "gpt-4o")
        self.assertEqual(config.base_url, "https://proxy.example/v1")
        self.assertEqual(config.temperature, 0.7)
        self.assertEqual(config.timeout_seconds, 15)
        self.assertEqual(config.max_retries, 5)
        self.assertEqual(config.rate_limit_per_minute, 20)
        self.assertEqual(config.credential_ref, "MY_SECRET")

    def test_invalid_env_values_raise_explicitly(self):
        for env in (
            {"AI_TEMPERATURE": "3.5"},
            {"AI_TIMEOUT_SECONDS": "0"},
            {"AI_MAX_RETRIES": "-1"},
            {"AI_RATE_LIMIT_PER_MINUTE": "0"},
            {"AI_TEMPERATURE": "abc"},
            {"AI_TIMEOUT_SECONDS": "abc"},
            {"AI_ENABLED": "maybe"},
        ):
            with self.subTest(env=env):
                with self.assertRaises(StructuredOutputError):
                    load_provider_config(env)

    def test_validate_rejects_invalid_config(self):
        bad = AIProviderConfig(
            name="", provider="nope", model_name="", temperature=3.0,
            timeout_seconds=0, max_retries=-1, rate_limit_per_minute=0,
        )
        with self.assertRaises(StructuredOutputError) as ctx:
            bad.validate()
        self.assertIn("provider", ctx.exception.message)
        self.assertIn("temperature", ctx.exception.message)

    def test_openai_compatible_requires_model(self):
        config = load_provider_config({"AI_PROVIDER": "openai_compatible"})
        self.assertEqual(config.model_name, "")
        with self.assertRaises(StructuredOutputError):
            config.validate()

    def test_resolved_base_url_for_each_provider(self):
        self.assertEqual(
            AIProviderConfig(name="a", provider="openai", model_name="gpt-4o-mini")
            .resolved_base_url(),
            "https://api.openai.com/v1",
        )
        self.assertEqual(
            AIProviderConfig(name="b", provider="deepseek", model_name="deepseek-chat")
            .resolved_base_url(),
            "https://api.deepseek.com/v1",
        )
        self.assertEqual(
            AIProviderConfig(
                name="c", provider="openai_compatible", model_name="m",
                base_url="https://local/v1/",
            ).resolved_base_url(),
            "https://local/v1",
        )

    def test_openai_compatible_without_base_url_raises(self):
        config = AIProviderConfig(
            name="c", provider="openai_compatible", model_name="m", base_url=None
        )
        with self.assertRaises(ConfigMissingError):
            config.resolved_base_url()

    def test_with_model(self):
        config = load_provider_config({"AI_PROVIDER": "deepseek"})
        changed = with_model(config, "deepseek-reasoner")
        self.assertEqual(changed.model_name, "deepseek-reasoner")
        self.assertEqual(config.model_name, "deepseek-chat")


class BillingTests(unittest.TestCase):
    def test_billing_approved_is_strict(self):
        self.assertTrue(billing_approved({"AI_BILLING_APPROVED": "true"}))
        self.assertTrue(billing_approved({"AI_BILLING_APPROVED": " TRUE "}))
        for value in ("false", "1", "yes", "", None):
            with self.subTest(value=value):
                env = {} if value is None else {"AI_BILLING_APPROVED": value}
                self.assertFalse(billing_approved(env))

    def test_ensure_billing_approved_raises(self):
        with self.assertRaises(BillingNotApprovedError):
            ensure_billing_approved({"AI_BILLING_APPROVED": "false"})
        ensure_billing_approved({"AI_BILLING_APPROVED": "true"})


class ReadinessHardConstraintTests(unittest.TestCase):
    """硬约束：缺 Key 或 AI_BILLING_APPROVED != true 必须抛明确错误。"""

    def _config(self):
        return load_provider_config({"AI_PROVIDER": "deepseek"})

    def test_missing_key_raises_config_missing(self):
        with self.assertRaises(ConfigMissingError) as ctx:
            assert_ready(self._config(), {"AI_BILLING_APPROVED": "true"})
        self.assertEqual(ctx.exception.code, "CONFIG_MISSING")
        fields = [d.field for d in ctx.exception.details]
        self.assertIn("AI_API_KEY", fields)
        self.assertIn("禁止伪造理解结果", ctx.exception.message)

    def test_billing_not_approved_raises(self):
        with self.assertRaises(BillingNotApprovedError) as ctx:
            assert_ready(self._config(), {"AI_API_KEY": "sk-test"})
        self.assertEqual(ctx.exception.code, "CONFIG_MISSING")
        fields = [d.field for d in ctx.exception.details]
        self.assertIn("AI_BILLING_APPROVED", fields)
        self.assertIn("计费", ctx.exception.message)

    def test_both_missing_lists_all_reasons(self):
        with self.assertRaises(ConfigMissingError) as ctx:
            assert_ready(self._config(), {})
        fields = [d.field for d in ctx.exception.details]
        self.assertIn("AI_API_KEY", fields)
        self.assertIn("AI_BILLING_APPROVED", fields)
        self.assertEqual(len(ctx.exception.details), 2)

    def test_disabled_provider_raises(self):
        config = load_provider_config({"AI_ENABLED": "false"})
        with self.assertRaises(ConfigMissingError):
            assert_ready(config, {"AI_API_KEY": "sk", "AI_BILLING_APPROVED": "true"})

    def test_ready_returns_real_key(self):
        key = assert_ready(
            self._config(), {"AI_API_KEY": "sk-real", "AI_BILLING_APPROVED": "true"}
        )
        self.assertEqual(key, "sk-real")

    def test_collect_readiness_problems_pure(self):
        problems = collect_readiness_problems(
            self._config(), {"AI_API_KEY": "sk", "AI_BILLING_APPROVED": "true"}
        )
        self.assertEqual(problems, [])

    def test_error_body_matches_contract(self):
        error = ConfigMissingError("缺少密钥", details=None)
        body = error.to_error_body("req-1")
        self.assertEqual(
            set(body["error"]),
            {"code", "message", "details", "request_id", "retryable"},
        )
        self.assertEqual(body["error"]["code"], "CONFIG_MISSING")
        self.assertEqual(body["error"]["request_id"], "req-1")
        self.assertFalse(body["error"]["retryable"])


if __name__ == "__main__":
    unittest.main()
