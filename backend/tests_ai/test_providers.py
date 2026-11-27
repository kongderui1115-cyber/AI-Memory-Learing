"""AI-01 三种 Provider 实现、请求构造与错误映射测试。

说明（质量红线）：
- 绝大多数用例是**真实纯逻辑**（请求构造、响应解析、错误映射、注册表）；
- 仅 ``test_complete_structured_with_fake_transport`` 使用 **MOCK**
  ``FakeTransport`` 隔离外部 HTTP，用于验证「请求构造 → 响应解析」链路，
  不联网、不产生费用、**不代表外部服务联调通过**。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _support  # noqa: E402  提供明确标注的 HTTP MOCK 与响应构造
from app.ai.config import AIProviderConfig  # noqa: E402
from app.ai.errors import (  # noqa: E402
    ConfigMissingError,
    ProviderAuthError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderServiceError,
    ProviderTimeoutError,
    StructuredOutputError,
)
from app.ai.ports import HttpResponse, StructuredRequest  # noqa: E402
from app.ai.providers.deepseek import DeepSeekProvider  # noqa: E402
from app.ai.providers.openai import OpenAIProvider  # noqa: E402
from app.ai.providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402
from app.ai.providers.registry import PROVIDER_CLASSES, resolve_provider  # noqa: E402


def _config(provider="openai", **overrides):
    data = {
        "name": "default",
        "provider": provider,
        "model_name": "gpt-4o-mini" if provider == "openai" else "deepseek-chat",
        "credential_ref": "AI_API_KEY",
        "temperature": 0.2,
        "timeout_seconds": 30,
        "max_retries": 3,
    }
    data.update(overrides)
    return AIProviderConfig(**data)


def _request():
    return StructuredRequest(
        operation="extract_knowledge",
        prompt_version="kp-extract-v1",
        system="只输出 JSON",
        user="笔记原文",
    )


class RegistryTests(unittest.TestCase):
    def test_three_registered_implementations(self):
        self.assertEqual(set(PROVIDER_CLASSES), {"openai", "deepseek", "openai_compatible"})
        self.assertIsInstance(resolve_provider(_config("openai")), OpenAIProvider)
        self.assertIsInstance(resolve_provider(_config("deepseek")), DeepSeekProvider)
        compatible = resolve_provider(
            _config("openai_compatible", base_url="https://local/v1", model_name="m")
        )
        self.assertIsInstance(compatible, OpenAICompatibleProvider)

    def test_unknown_provider_raises(self):
        with self.assertRaises(StructuredOutputError):
            resolve_provider(_config("nope"))

    def test_openai_compatible_requires_base_url(self):
        with self.assertRaises(ConfigMissingError):
            resolve_provider(_config("openai_compatible", model_name="m", base_url=None))

    def test_capabilities_contain_no_secret(self):
        provider = resolve_provider(_config("deepseek"))
        caps = provider.capabilities()
        self.assertEqual(caps["provider"], "deepseek")
        self.assertEqual(caps["model"], "deepseek-chat")
        self.assertNotIn("api_key", json.dumps(caps).lower())


class BuildRequestTests(unittest.TestCase):
    def test_headers_and_payload(self):
        provider = resolve_provider(_config("openai"))
        url, headers, body = provider.build_request(_request(), api_key="sk-test")
        self.assertEqual(url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        payload = json.loads(body)
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(payload["messages"][0]["content"], "只输出 JSON")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["temperature"], 0.2)

    def test_json_mode_difference_between_providers(self):
        openai_payload = json.loads(
            resolve_provider(_config("openai")).build_request(_request(), api_key="k")[2]
        )
        compatible_payload = json.loads(
            resolve_provider(
                _config("openai_compatible", base_url="https://local/v1", model_name="m")
            ).build_request(_request(), api_key="k")[2]
        )
        self.assertIn("response_format", openai_payload)
        self.assertNotIn("response_format", compatible_payload)
        self.assertIn("只输出一个 JSON 对象", compatible_payload["messages"][0]["content"])

    def test_custom_auth_header_for_compatible_endpoint(self):
        provider = OpenAICompatibleProvider(
            _config("openai_compatible", base_url="https://azure/v1", model_name="m"),
            transport=_support.FakeTransport(),  # MOCK：仅满足构造，不发起调用
            auth_header="api-key",
            auth_scheme="",
        )
        _, headers, _ = provider.build_request(_request(), api_key="xyz")
        self.assertEqual(headers["api-key"], "xyz")

    def test_missing_api_key_raises_and_no_transport_call(self):
        fake = _support.FakeTransport([_support.ai_success_response({"ok": True})])
        provider = OpenAIProvider(_config("openai"), transport=fake)
        with self.assertRaises(ConfigMissingError):
            provider.build_request(_request(), api_key="")
        self.assertEqual(fake.calls, [])


class ParseResponseTests(unittest.TestCase):
    def test_success_parses_content_and_tokens(self):
        provider = resolve_provider(_config("openai"))
        response = _support.ai_success_response(
            {"knowledge_points": [{"title": "T"}]}, input_tokens=13, output_tokens=5
        )
        result = provider.parse_response(response)
        self.assertEqual(result.parsed["knowledge_points"][0]["title"], "T")
        self.assertEqual(result.input_tokens, 13)
        self.assertEqual(result.output_tokens, 5)
        self.assertEqual(result.total_tokens, 18)
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.provider, "openai")

    def test_http_error_mapping(self):
        provider = resolve_provider(_config("openai"))
        expected = {
            401: ProviderAuthError,
            403: ProviderAuthError,
            408: ProviderTimeoutError,
            429: ProviderRateLimitedError,
            500: ProviderServiceError,
            400: ProviderResponseError,
        }
        for status, error_type in expected.items():
            with self.subTest(status=status):
                with self.assertRaises(error_type) as ctx:
                    provider.parse_response(_support.http_error_response(status))
                self.assertEqual(ctx.exception.retryable, error_type.retryable)

    def test_non_json_body_rejected(self):
        provider = resolve_provider(_config("openai"))
        with self.assertRaises(ProviderResponseError):
            provider.parse_response(HttpResponse(200, b"not-json"))

    def test_missing_choices_rejected(self):
        provider = resolve_provider(_config("openai"))
        with self.assertRaises(ProviderResponseError):
            provider.parse_response(HttpResponse(200, b'{"usage": {}}'))

    def test_non_object_structured_output_rejected(self):
        provider = resolve_provider(_config("openai"))
        raw = {
            "choices": [{"message": {"content": "[1,2,3]"}, "finish_reason": "stop"}],
            "usage": {},
        }
        with self.assertRaises(ProviderResponseError):
            provider.parse_response(
                HttpResponse(200, json.dumps(raw).encode("utf-8"))
            )

    def test_complete_structured_with_fake_transport(self):
        """MOCK：FakeTransport 仅隔离外部 HTTP，验证请求构造→响应解析链路。

        不联网、不调用 OpenAI/DeepSeek、不产生费用，**不代表外部联调通过**；
        真实联调为 AI-07，需用户授权 BLK-02 后另行执行。
        """
        fake = _support.FakeTransport(
            [_support.ai_success_response({"items": []}, input_tokens=9, output_tokens=4)]
        )
        provider = OpenAIProvider(_config("openai", timeout_seconds=12), transport=fake)
        result = provider.complete_structured(_request(), api_key="sk-mock")
        self.assertEqual(result.parsed, {"items": []})
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(fake.calls[0]["timeout_seconds"], 12.0)
        self.assertEqual(fake.calls[0]["headers"]["Authorization"], "Bearer sk-mock")


if __name__ == "__main__":
    unittest.main()
