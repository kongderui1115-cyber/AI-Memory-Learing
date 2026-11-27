"""NOTIF-01 渠道注册表：按 channel_type 解析插件，新增渠道不改核心编排。"""

from __future__ import annotations

from typing import Callable

from .errors import ChannelNotRegisteredError
from .ports import NotificationChannel

ChannelFactory = Callable[[], NotificationChannel]


class ChannelRegistry:
    """channel_type -> 工厂。resolve() 每次返回新实例（渠道无状态，线程安全）。"""

    def __init__(self) -> None:
        self._factories: dict[str, ChannelFactory] = {}

    def register(
        self,
        channel_type: str,
        factory: ChannelFactory,
        *,
        replace: bool = False,
    ) -> None:
        if not channel_type:
            raise ValueError("channel_type 不能为空")
        if not callable(factory):
            raise TypeError("factory 必须可调用（渠道类或无参工厂函数）")
        if channel_type in self._factories and not replace:
            raise ValueError(
                f"channel_type={channel_type!r} 已注册；如需覆盖请传 replace=True"
            )
        self._factories[channel_type] = factory

    def resolve(self, channel_type: str) -> NotificationChannel:
        factory = self._factories.get(channel_type)
        if factory is None:
            raise ChannelNotRegisteredError(channel_type, self.registered_types())
        return factory()

    def has(self, channel_type: str) -> bool:
        return channel_type in self._factories

    def registered_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))
