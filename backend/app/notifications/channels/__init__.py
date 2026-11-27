"""内置渠道注册（NOTIF-03 / NOTIF-04）。

FR-07 微信优先 4 种 + FR-08 钉钉 2 种 + SMTP 1 种，共 7 种 channel_type，
与冻结契约 NotificationChannelType 一一对应。

FR-08 的「企业微信」由 wecom_app（应用消息）/ wecom_webhook（群机器人）承载，
它们同时是 FR-07 的路径 A / D，属于同一套实现，不重复造轮子。
"""

from __future__ import annotations

from ..registry import ChannelRegistry
from .dingtalk import DingtalkAppChannel, DingtalkWebhookChannel
from .smtp import SmtpChannel
from .wechat import (
    ThirdPartyPushChannel,
    WecomAppChannel,
    WecomWebhookChannel,
    WechatOfficialAccountChannel,
)

BUILTIN_CHANNELS = (
    WecomAppChannel,
    WechatOfficialAccountChannel,
    ThirdPartyPushChannel,
    WecomWebhookChannel,
    DingtalkWebhookChannel,
    DingtalkAppChannel,
    SmtpChannel,
)


def register_builtins(registry: ChannelRegistry, *, replace: bool = False) -> ChannelRegistry:
    for cls in BUILTIN_CHANNELS:
        registry.register(cls.channel_type, cls, replace=replace)
    return registry


def default_registry() -> ChannelRegistry:
    return register_builtins(ChannelRegistry())
