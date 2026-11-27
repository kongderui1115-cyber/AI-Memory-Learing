"""OpenAI 协议族共用的**真实**调用路径（标准库 urllib）。

- ``UrllibTransport`` 是真实 HTTP 传输，仅在凭据与计费授权齐备后才会被
  ``AIExecutionService`` 调用；本模块自身绝不主动联网、不产生费用。
- 三种 Provider（OpenAI / DeepSeek / OpenAI-compatible）共享本协议实现，
  差异仅在于默认端点、默认模型与是否启用 JSON mode，业务代码无需改动。
- 任何失败都抛显式错误；缺 api_key 或响应不可解析时绝不返回伪造结果。
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from app.outbound_http import open_authenticated

from ..config import AIProviderConfig
from ..errors import (
    ConfigMissingError,
    ErrorDetail,
    ProviderResponseError,
    ProviderTimeoutError,
    error_from_http_status,
)
from ..ports import (
    AIProvider,
    HttpResponse,
    ProviderResult,
    StructuredRequest,
    Transport,
)


class UrllibTransport(Transport):
    """基于标准库 ``urllib.request`` 的真实 HTTP POST 传输。"""

    def post(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with open_authenticated(request, timeout=timeout_seconds) as response:
                return HttpResponse(
                    status_code=response.status,
                    body=response.read(),
                    headers=dict(response.headers),
                )
        except urllib.error.HTTPError as exc:
            # HTTPError 也是 URLError 子类，必须先捕获；交回给 parse_response 统一映射。
            return HttpResponse(
                status_code=exc.code,
                body=exc.read(),
                headers=dict(exc.headers) if exc.headers else {},
            )
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise ProviderTimeoutError(
                f"外部 AI API 连接/读取超时或网络不可达（timeout={timeout_seconds}s）: {exc}"
            ) from exc


class OpenAIProtocolProvider(AIProvider):
    """OpenAI chat-completions 协议的共用实现。

    子类只需声明 ``provider_type`` / ``default_base_url`` / ``default_model`` /
    ``supports_json_mode``。``api_key`` 在调用时传入，绝不写入配置对象。
    """

    provider_type: str = ""
    default_base_url: str = ""
    default_model: str = ""
    supports_json_mode: bool = True

    def __init__(
        self,
        config: AIProviderConfig,
        transport: Transport | None = None,
        *,
        extra_headers: dict[str, str] | None = None,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
    ) -> None:
        self.config = config
        self._auth_header = auth_header
        self._auth_scheme = auth_scheme
        base_url = config.base_url or self.default_base_url
        if not base_url:
            raise ConfigMissingError(
                "openai_compatible 必须配置 AI_BASE_URL（兼容端点地址）",
                details=[ErrorDetail("AI_BASE_URL", "required")],
            )
        model = config.model_name or self.default_model
        if not model:
            raise ConfigMissingError(
                "未配置模型名（AI_MODEL），拒绝猜测模型",
                details=[ErrorDetail("AI_MODEL", "required")],
            )
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self._transport: Transport = transport or UrllibTransport()
        self._extra_headers = dict(extra_headers or {})

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def build_request(
        self, request: StructuredRequest, *, api_key: str
    ) -> tuple[str, dict[str, str], bytes]:
        """构造一次真实 HTTP 请求（纯逻辑，可单测）。"""
        if not api_key:
            raise ConfigMissingError(
                "API Key 为空，已阻止真实调用；不得返回伪造的理解结果",
                details=[ErrorDetail("api_key", "empty")],
            )
        headers = {
            self._auth_header: f"{self._auth_scheme} {api_key}".strip(),
            "Content-Type": "application/json",
        }
        headers.update(self._extra_headers)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": (
                self.config.temperature
                if request.temperature is None
                else request.temperature
            ),
            "stream": False,
        }
        if self.supports_json_mode:
            payload["response_format"] = {"type": "json_object"}
        else:
            # 兼容端点不一定支持 JSON mode，改为在 system 提示里要求纯 JSON 输出。
            payload["messages"][0]["content"] = (
                request.system + "\n只输出一个 JSON 对象，不要输出任何其它文字。"
            )
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self.endpoint, headers, body

    def capabilities(self) -> dict[str, Any]:
        """供 ``POST /ai/providers/{id}/validate`` 使用的能力摘要（不含密钥）。"""
        return {
            "provider": self.provider_type,
            "model": self.model_name,
            "endpoint": self.endpoint,
            "json_mode": self.supports_json_mode,
            "timeout_seconds": self.config.timeout_seconds,
            "max_retries": self.config.max_retries,
            "auth_header": self._auth_header,
        }

    def parse_response(self, response: HttpResponse) -> ProviderResult:
        """解析真实 HTTP 响应为 ``ProviderResult``（纯逻辑）。"""
        if not (200 <= response.status_code < 300):
            snippet = response.body.decode("utf-8", errors="replace")[:300]
            raise error_from_http_status(
                response.status_code,
                f"外部 AI API 返回 HTTP {response.status_code}: {snippet}",
            )
        try:
            raw = response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderResponseError("外部 AI API 响应不是合法 JSON") from exc
        if not isinstance(raw, dict):
            raise ProviderResponseError("外部 AI API 响应顶层必须为对象")
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                "外部 AI API 响应缺少 choices[0].message.content"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError("模型返回内容为空，拒绝伪造结果")
        try:
            parsed = json.loads(content)
        except ValueError as exc:
            raise ProviderResponseError(
                "模型返回内容不是合法 JSON（结构化输出校验失败）"
            ) from exc
        if not isinstance(parsed, dict):
            raise ProviderResponseError("模型结构化输出顶层必须为 JSON 对象")

        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        return ProviderResult(
            content=content,
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self.model_name,
            provider=self.provider_type,
            finish_reason=raw.get("choices", [{}])[0].get("finish_reason")
            if isinstance(raw.get("choices"), list) and raw["choices"]
            else None,
            raw=raw,
        )

    def complete_structured(
        self, request: StructuredRequest, *, api_key: str
    ) -> ProviderResult:
        """执行一次真实调用。业务入口必须先经 ``AIExecutionService`` 的就绪校验。"""
        url, headers, body = self.build_request(request, api_key=api_key)
        response = self._transport.post(
            url, headers, body, float(self.config.timeout_seconds)
        )
        return self.parse_response(response)
