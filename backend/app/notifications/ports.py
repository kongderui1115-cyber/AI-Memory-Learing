"""通知插件端口与跨模块数据结构（NOTIF-01）。

领域层只依赖这里定义的抽象，不依赖 FastAPI / SQLAlchemy / 任何具体 SDK：
- NotificationChannel：渠道插件抽象基类（新增渠道实现它并在注册表登记即可，不改核心编排）。
- RenderedMessage / SendResult：编排与插件之间的数据契约。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 仅类型注解，避免运行时循环导入
    from .config import ChannelConfig
    from .transports import HttpTransport, SmtpTransport


@dataclass(frozen=True)
class RenderedMessage:
    """一条待发消息（已渲染、已按渠道长度裁剪/分段）。"""

    title: str
    body: str
    part_index: int = 1
    part_total: int = 1
    review_url: str | None = None

    def full_text(self) -> str:
        """标题 + 正文；每条分段消息都带标题，保证可读性（FR-07）。"""
        return f"{self.title}\n\n{self.body}" if self.title else self.body


@dataclass
class SendResult:
    """渠道 send() 的返回。失败主要由异常承载，成功时 ok=True。

    request_metadata / response_metadata 必须已脱敏（不得含 token/secret/webhook 全文），
    对应 notification_deliveries.request_metadata / response_metadata 字段。
    """

    ok: bool
    provider_message_id: str | None = None
    request_metadata: dict[str, Any] = field(default_factory=dict)
    response_metadata: dict[str, Any] = field(default_factory=dict)


class NotificationChannel(ABC):
    """NOTIF-01 插件端口。

    新增渠道只需：
      1) 继承 BaseChannel（或本类）并实现 send / _send；
      2) 在 ChannelRegistry 登记 channel_type 工厂；
    核心编排（worker / registry / template）无需改动。
    """

    channel_type: str = ""
    #: 该渠道正文长度上限（None = 不限）；length_unit 决定按字符还是 UTF-8 字节。
    max_length: int | None = None
    length_unit: str = "char"

    @abstractmethod
    def validate_config(self, config: "ChannelConfig") -> None:
        """校验凭据/配置；缺凭据必须抛 ConfigMissingError，绝不发请求。"""

    @abstractmethod
    def send(
        self,
        message: RenderedMessage,
        config: "ChannelConfig",
        http: "HttpTransport",
        smtp: "SmtpTransport",
    ) -> SendResult:
        """发送一条消息；返回 SendResult 或抛 NotificationError 子类。"""
