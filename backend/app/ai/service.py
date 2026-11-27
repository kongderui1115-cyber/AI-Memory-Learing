"""AI 调用执行用例（业务层唯一入口）：就绪校验 → 限流 → 重试 → 调用日志。

硬约束在此落实：``assert_ready`` 未通过（缺 Key / 未授权计费 / 禁用）时
直接抛 ``CONFIG_MISSING``，**不创建调用日志、不发起真实 HTTP、不返回任何
伪造的理解结果**。只有全部前置条件满足才解析到具体 Provider 并真实调用。

重试只针对显式 ``retryable`` 的错误；每次尝试与最终状态都写入
``AICallLog``（追加式审计）。``transport`` / ``sleeper`` / ``clock`` 可注入，
便于用 unittest 隔离外部 HTTP，但注入不改变「缺凭据即报错」的行为。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from .call_log import AICallLog, CallRecorder
from .config import AIProviderConfig, assert_ready
from .errors import (
    AIIntegrationError,
    ProviderRateLimitedError,
    ProviderResponseError,
)
from .ports import AIProvider, ProviderResult, StructuredRequest, Transport
from .providers.registry import resolve_provider
from .retry import RateLimiter, RetryPolicy


@dataclass(frozen=True)
class CompletedCall:
    """一次已完成调用的真实结果与追加写审计记录。"""

    result: ProviderResult
    call_log: AICallLog


class AIExecutionService:
    """把配置、Provider 端口、重试/限流与审计日志编排起来的用例。"""

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        transport: Transport | None = None,
        sleeper: Callable[[float], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        limiter_clock: Callable[[], float] | None = None,
    ) -> None:
        self._env = env
        # 生产：真实 urllib 传输 + 真实退避等待；测试可注入替身隔离 I/O。
        self._transport = transport
        self._sleeper: Callable[[float], Any] = sleeper if sleeper is not None else time.sleep
        self._clock = clock
        self._limiter_clock = limiter_clock
        self._limiters: dict[str, RateLimiter] = {}

    def _env_mapping(self) -> Mapping[str, str]:
        return os.environ if self._env is None else self._env

    def resolve_provider(self, config: AIProviderConfig) -> AIProvider:
        """仅解析实现，不发起网络请求。"""
        return resolve_provider(config, transport=self._transport)

    def _limiter_for(self, config: AIProviderConfig) -> RateLimiter:
        key = config.config_id or config.name
        limiter = self._limiters.get(key)
        if limiter is None or limiter.per_minute != config.rate_limit_per_minute:
            limiter = RateLimiter(config.rate_limit_per_minute, clock=self._limiter_clock)
            self._limiters[key] = limiter
        return limiter

    def complete(
        self, config: AIProviderConfig, request: StructuredRequest
    ) -> CompletedCall:
        """执行一次真实结构化调用。

        Raises:
            ConfigMissingError / BillingNotApprovedError: 前置条件不满足（绝不伪造结果）。
            AIIntegrationError: 外部调用失败，已记录失败日志。
        """
        # (1) 硬约束：未配置 Key 或 AI_BILLING_APPROVED != true 直接报错。
        api_key = assert_ready(config, self._env_mapping())
        provider = self.resolve_provider(config)

        # (2) 审计记录（追加写；此处之后才可能发生外部调用）。
        recorder = CallRecorder(
            operation=request.operation,
            provider=config.provider,
            model_name=config.model_name,
            prompt_version=request.prompt_version,
            provider_config_id=config.config_id or config.name,
            metadata={
                "provider_type": config.provider,
                "operation": request.operation,
                "prompt_version": request.prompt_version,
            },
            clock=self._clock,
        )
        recorder.start()

        # (3) 速率限制：超配额返回契约 429，不静默排队伪造成功。
        limiter = self._limiter_for(config)
        if not limiter.try_acquire():
            error = ProviderRateLimitedError(
                "AI Provider 速率限制已触发（rate_limit_per_minute="
                f"{config.rate_limit_per_minute}），请稍后重试",
            )
            recorder.fail(error)
            error.call_log = recorder.log
            raise error

        # (4) 真实调用 + 只对可重试错误做指数退避重试。
        policy = RetryPolicy(max_retries=config.max_retries)
        attempt = 1
        while True:
            try:
                result = provider.complete_structured(request, api_key=api_key)
            except AIIntegrationError as error:
                if policy.should_retry(error, attempt):
                    recorder.retry()
                    self._sleeper(policy.backoff_seconds(attempt))
                    attempt += 1
                    continue
                recorder.fail(error)
                error.call_log = recorder.log
                raise
            except Exception as error:  # 未预期异常同样留痕并显式上报
                wrapped = ProviderResponseError(
                    f"外部 AI 调用发生未预期错误: {type(error).__name__}: {error}"
                )
                recorder.fail(wrapped)
                wrapped.call_log = recorder.log
                raise wrapped from error
            recorder.succeed(result)
            return CompletedCall(result=result, call_log=recorder.log)
