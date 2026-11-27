"""AI 层端口（抽象）与跨层数据结构。

业务用例只依赖 ``AIProvider`` 端口；具体供应商、HTTP 传输与重试/限流
均由基础设施适配器实现。本模块只使用标准库。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StructuredRequest:
    """一次结构化 LLM 调用的输入。

    ``operation`` 对应 ``ai_call_logs.operation``；``prompt_version`` 落入
    ``ai_call_logs.prompt_version`` 与生成来源元数据；``response_schema_hint``
    描述期望的 JSON 结构（用于 JSON-mode 提示与输出校验）。
    """

    operation: str
    prompt_version: str
    system: str
    user: str
    response_schema_hint: dict[str, Any] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResult:
    """单次 Provider 调用的真实结果（不含伪造兜底）。"""

    content: str
    parsed: dict[str, Any] | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    model_name: str
    provider: str
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HttpResponse:
    """外部 HTTP 响应的最小抽象，便于注入测试替身隔离网络。"""

    status_code: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class Transport(ABC):
    """可注入的 HTTP 传输端口。

    生产实现为 ``providers.base.UrllibTransport``；单元测试注入
    ``FakeTransport`` 仅用于隔离外部 HTTP，不代表外部联调通过。
    """

    @abstractmethod
    def post(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpResponse:
        """发起一次 POST；超时由 ``timeout_seconds`` 统一约束。"""
        raise NotImplementedError


@dataclass(frozen=True)
class GenerationMeta:
    """生成来源元数据，写入知识点/题目与 ``ai_call_logs`` 关联。"""

    prompt_version: str = ""
    provider: str = ""
    model_name: str | None = None
    provider_config_id: str | None = None
    ai_call_log_id: str | None = None

    @classmethod
    def from_call(cls, result: "ProviderResult", call_log: Any = None) -> "GenerationMeta":
        return cls(
            provider=result.provider,
            model_name=result.model_name,
            provider_config_id=getattr(call_log, "provider_config_id", None),
            ai_call_log_id=getattr(call_log, "id", None),
        )


class AIProvider(ABC):
    """AI Provider 抽象端口（架构 §7 ``complete_structured``）。

    Openai / DeepSeek / OpenAI-compatible 三种实现共享此端口，
    业务层切换供应商无需改代码。
    """

    provider_type: str = ""
    model_name: str = ""

    @abstractmethod
    def complete_structured(
        self, request: StructuredRequest, *, api_key: str
    ) -> ProviderResult:
        """执行一次真实结构化调用；任何失败抛显式错误，不返回假数据。"""
        raise NotImplementedError
