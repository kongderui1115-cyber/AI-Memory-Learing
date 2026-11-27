"""测试替身（TEST DOUBLE）—— 仅隔离 HTTP / SMTP，不代表真实送达。

重要声明：
- 本文件中的 Fake* 只用于在单元测试里拦截 I/O、断言「请求构造 / 编排逻辑」。
- 它们不发起任何真实网络请求，也不证明「真实推送成功」。
- 真实渠道联调（NOTIF-07）需用户授权 BLK-03 / BLK-04 后另做；授权前一律标为未验证。
- 测试用 URL / 邮箱均为 RFC 2606 保留域（example.invalid 等），不会触达真实服务。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.config import ChannelConfig  # noqa: E402
from app.notifications.content import (  # noqa: E402
    DEFAULT_BODY_TEMPLATE,
    DEFAULT_TITLE_TEMPLATE,
    KnowledgeContent,
)
from app.notifications.ports import RenderedMessage  # noqa: E402
from app.notifications.transports import (  # noqa: E402
    HttpResult,
    HttpTransport,
    SmtpEnvelope,
    SmtpResult,
    SmtpTransport,
)
from app.notifications.worker import NotificationTemplate  # noqa: E402


@dataclass(frozen=True)
class RecordedCall:
    method: str
    url: str
    headers: dict
    body: str | None
    timeout: float


class FakeHttpTransport(HttpTransport):
    """隔离 HTTP 的测试替身：脚本化响应 / 记录调用，不发真实请求。"""

    def __init__(self, script=None, *, default_status=200, default_body=None) -> None:
        self.script = list(script or [])
        self.default = HttpResult(
            default_status,
            default_body if default_body is not None
            else json.dumps({"errcode": 0, "errmsg": "ok"}),
        )
        self.calls: list[RecordedCall] = []

    def request(self, method, url, *, headers=None, body=None, timeout=10.0) -> HttpResult:
        self.calls.append(RecordedCall(method.upper(), url, dict(headers or {}), body, timeout))
        item = self.script.pop(0) if self.script else self.default
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def json_bodies(self) -> list[dict]:
        return [json.loads(call.body) for call in self.calls if call.body]


class FakeSmtpTransport(SmtpTransport):
    """隔离 SMTP 的测试替身：记录 envelope，不发真实邮件。"""

    def __init__(self, result: SmtpResult | None = None) -> None:
        self.result = result or SmtpResult(True, provider_message_id="fake-msg-id")
        self.envelopes: list[SmtpEnvelope] = []

    def send(self, envelope: SmtpEnvelope) -> SmtpResult:
        self.envelopes.append(envelope)
        return self.result


def make_content(**overrides) -> KnowledgeContent:
    base = dict(
        title="Windows 内核：IRQL 与 DPC 的关系",
        summary="IRQL 是中断请求级别；DPC 在 DISPATCH_LEVEL 执行，不能访问分页内存。",
        question="为什么 DPC 例程不能访问分页内存？",
        answer_points="DISPATCH_LEVEL 及以上禁止缺页异常，访问分页内存可能触发页面错误并导致死锁或蓝屏。",
        review_url="https://example.invalid/review/task-001",
        explanation="调度器在 DISPATCH_LEVEL 运行 DPC，此时无法等待分页 I/O 完成。",
        subject="Windows 内核",
        knowledge_point_id="kp-001",
        task_id="task-001",
        review_item_id="ri-001",
    )
    base.update(overrides)
    return KnowledgeContent(**base)


def make_message(**overrides) -> RenderedMessage:
    base = dict(title="【复习提醒】IRQL 与 DPC", body="【答案要点】不能访问分页内存，因为 DISPATCH_LEVEL 禁止缺页。")
    base.update(overrides)
    return RenderedMessage(**base)


def make_config(channel_type="wecom_webhook", **overrides) -> ChannelConfig:
    base = dict(
        name="test-channel",
        channel_type=channel_type,
        credential_ref="WECOM",
        settings={},
        user_id="user-1",
    )
    base.update(overrides)
    return ChannelConfig(**base)


def make_template(**overrides) -> NotificationTemplate:
    base = dict(
        channel_type="wecom_webhook",
        template_key="daily_review",
        title_template=DEFAULT_TITLE_TEMPLATE,
        body_template=DEFAULT_BODY_TEMPLATE,
    )
    base.update(overrides)
    return NotificationTemplate(**base)
