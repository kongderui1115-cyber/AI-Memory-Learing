"""AI Learning Memory OS — 通知模块（NOTIF-01 ~ NOTIF-05）。

零外部依赖、仅标准库即可导入与单测（详见 contract_values.py 说明）。

分层：
  ports / registry / config      NOTIF-01 插件端口、注册表、渠道配置
  template / content             NOTIF-02 模板渲染、长度自适应、FR-07 具体内容
  channels/                      NOTIF-03 微信优先 4 种 + NOTIF-04 钉钉/企业微信/SMTP
  jobs / retry / worker          NOTIF-05 任务、退避重试、失败记录、历史追踪
  transports                     隔离 HTTP/SMTP 的端口与标准库生产实现

合规声明：
- 个人微信无官方主动推送 API；不实现逆向协议，不返回「假推送成功」。
- 未配置任何凭据时抛 ConfigMissingError（CONFIG_MISSING），绝不发请求。
- 本批次不安装依赖、不联网、不调用外部通知 API、不连接数据库、不发真实消息。
"""

from __future__ import annotations

from .channels import BUILTIN_CHANNELS, default_registry, register_builtins
from .config import ChannelConfig
from .content import (
    DEFAULT_BODY_TEMPLATE,
    DEFAULT_TITLE_TEMPLATE,
    KnowledgeContent,
    assert_concrete,
    build_context,
    validate_rendered_content,
)
from .contract_values import (
    ChannelType,
    DeliveryStatus,
    JobStatus,
    WECHAT_CHANNEL_TYPES,
    WECOM_CHANNEL_TYPES,
    assert_contract_alignment,
    load_frozen_enums,
)
from .errors import (
    ChannelDeliveryError,
    ChannelDisabledError,
    ChannelNotRegisteredError,
    ConfigMissingError,
    EmptyContentError,
    NotificationError,
    TemplateRenderError,
)
from .jobs import (
    InMemoryJobRepository,
    JobRepository,
    NotificationDelivery,
    NotificationJob,
)
from .ports import NotificationChannel, RenderedMessage, SendResult
from .registry import ChannelRegistry
from .retry import (
    RetryPolicy,
    backoff_delays,
    is_retryable_status,
    next_attempt_at,
    should_retry,
)
from .template import TemplateRenderer, byte_sizer, char_sizer, split_segments, truncate
from .transports import (
    HttpResult,
    HttpTransport,
    SmtpEnvelope,
    SmtpResult,
    SmtpTransport,
    SmtplibTransport,
    UrllibHttpTransport,
    mask,
    redact_mapping,
    safe_url,
)
from .worker import NotificationTemplate, NotificationWorker

__all__ = [
    "BUILTIN_CHANNELS",
    "ChannelConfig",
    "ChannelDeliveryError",
    "ChannelDisabledError",
    "ChannelNotRegisteredError",
    "ChannelRegistry",
    "ChannelType",
    "ConfigMissingError",
    "DEFAULT_BODY_TEMPLATE",
    "DEFAULT_TITLE_TEMPLATE",
    "DeliveryStatus",
    "EmptyContentError",
    "HttpResult",
    "HttpTransport",
    "InMemoryJobRepository",
    "JobRepository",
    "JobStatus",
    "KnowledgeContent",
    "NotificationChannel",
    "NotificationDelivery",
    "NotificationError",
    "NotificationJob",
    "NotificationTemplate",
    "NotificationWorker",
    "RenderedMessage",
    "RetryPolicy",
    "SendResult",
    "SmtpEnvelope",
    "SmtpResult",
    "SmtpTransport",
    "SmtplibTransport",
    "TemplateRenderError",
    "TemplateRenderer",
    "UrllibHttpTransport",
    "WECHAT_CHANNEL_TYPES",
    "WECOM_CHANNEL_TYPES",
    "assert_concrete",
    "assert_contract_alignment",
    "backoff_delays",
    "build_context",
    "byte_sizer",
    "char_sizer",
    "default_registry",
    "is_retryable_status",
    "load_frozen_enums",
    "mask",
    "next_attempt_at",
    "redact_mapping",
    "register_builtins",
    "safe_url",
    "should_retry",
    "split_segments",
    "truncate",
    "validate_rendered_content",
]
