"""注册表按 channel_type 解析 + 插件式扩展测试（NOTIF-01）。"""

import os
import sys
import unittest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.channels import default_registry  # noqa: E402
from app.notifications.contract_values import ChannelType  # noqa: E402
from app.notifications.errors import ChannelNotRegisteredError  # noqa: E402
from app.notifications.ports import NotificationChannel, SendResult  # noqa: E402
from app.notifications.registry import ChannelRegistry  # noqa: E402


class _ProbeChannel(NotificationChannel):
    """仅用于验证「新增渠道不改核心编排」的探针，不是冻结契约内的合规渠道。"""

    channel_type = "probe_unregistered_type"

    def validate_config(self, config):
        return None

    def send(self, message, config, http, smtp):
        return SendResult(True)


class RegistryTest(unittest.TestCase):
    def test_resolve_every_builtin_channel(self):
        registry = default_registry()
        for channel_type in ChannelType.ALL:
            channel = registry.resolve(channel_type)
            self.assertIsInstance(channel, NotificationChannel)
            self.assertEqual(channel.channel_type, channel_type)

    def test_resolve_returns_fresh_instance(self):
        registry = default_registry()
        first = registry.resolve(ChannelType.WECOM_WEBHOOK)
        second = registry.resolve(ChannelType.WECOM_WEBHOOK)
        self.assertIsNot(first, second)

    def test_unknown_type_raises_with_registered_list(self):
        registry = default_registry()
        with self.assertRaises(ChannelNotRegisteredError) as ctx:
            registry.resolve("no_such_channel")
        self.assertEqual(ctx.exception.channel_type, "no_such_channel")
        self.assertIn("wecom_webhook", str(ctx.exception))

    def test_duplicate_registration_rejected_unless_replace(self):
        registry = ChannelRegistry()
        registry.register("x", _ProbeChannel)
        with self.assertRaises(ValueError):
            registry.register("x", _ProbeChannel)
        registry.register("x", _ProbeChannel, replace=True)
        self.assertTrue(registry.has("x"))

    def test_empty_type_and_non_callable_rejected(self):
        registry = ChannelRegistry()
        with self.assertRaises(ValueError):
            registry.register("", _ProbeChannel)
        with self.assertRaises(TypeError):
            registry.register("y", object())

    def test_new_channel_does_not_change_core_orchestration(self):
        # 注册表本身开放扩展：登记一个新类型即可 resolve，核心代码无需改动。
        # 注意：这只是机制验证；新类型纳入冻结契约须先改文档/enums.py/前端类型。
        registry = default_registry()
        registry.register(_ProbeChannel.channel_type, _ProbeChannel)
        channel = registry.resolve(_ProbeChannel.channel_type)
        self.assertIsInstance(channel, _ProbeChannel)
        self.assertIn(_ProbeChannel.channel_type, registry.registered_types())


if __name__ == "__main__":
    unittest.main()
