"""缺凭据报错路径测试（FR-07 / FR-08 硬约束）。

核心断言：未配置任何凭据时，每个渠道都必须在发起任何 I/O 之前抛
ConfigMissingError（CONFIG_MISSING），且测试替身的 transport 调用次数为 0。
即「绝不假推送成功、绝不静默降级」。
"""

import os
import sys
import unittest
from unittest.mock import patch

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.channels import default_registry  # noqa: E402
from app.notifications.config import ChannelConfig  # noqa: E402
from app.notifications.contract_values import ChannelType  # noqa: E402
from app.notifications.errors import (  # noqa: E402
    ChannelDisabledError,
    ConfigMissingError,
)
from app.notifications.ports import RenderedMessage  # noqa: E402

try:
    from .fakes import FakeHttpTransport, FakeSmtpTransport  # noqa: E402
except (ImportError, ValueError):
    from fakes import FakeHttpTransport, FakeSmtpTransport  # noqa: E402


#: (channel_type, credential_ref, 满足非秘密 settings 的最小配置)
CASES = (
    (ChannelType.WECOM_APP, "WECOM", {"touser": "@all"}),
    (ChannelType.WECHAT_OFFICIAL_ACCOUNT, "WECHAT", {"touser": "openid", "template_id": "TPL"}),
    (ChannelType.THIRD_PARTY_PUSH, "THIRD_PARTY_PUSH", {}),
    (ChannelType.WECOM_WEBHOOK, "WECOM", {}),
    (ChannelType.DINGTALK_WEBHOOK, "DINGTALK", {}),
    (ChannelType.DINGTALK_APP, "DINGTALK", {"agent_id": "1", "userid_list": "u1"}),
    (ChannelType.SMTP, "SMTP", {
        "to_addresses": ["learner@example.invalid"],
        "host": "smtp.example.invalid",
        "from_addr": "noreply@example.invalid",
    }),
)

MESSAGE = RenderedMessage("复习提醒：IRQL", "【答案要点】DISPATCH_LEVEL 禁止缺页异常。")


class MissingCredentialsTest(unittest.TestCase):
    def test_every_channel_raises_and_never_touches_transport(self):
        # clear=True 模拟「用户未授权任何凭据」的环境；本套件不发真实请求
        with patch.dict(os.environ, {}, clear=True):
            registry = default_registry()
            for channel_type, ref, settings in CASES:
                with self.subTest(channel_type=channel_type):
                    channel = registry.resolve(channel_type)
                    config = ChannelConfig(
                        name="test", channel_type=channel_type,
                        credential_ref=ref, settings=settings,
                    )
                    http = FakeHttpTransport()
                    smtp = FakeSmtpTransport()
                    with self.assertRaises(ConfigMissingError) as ctx:
                        channel.send(MESSAGE, config, http, smtp)
                    self.assertEqual(ctx.exception.code, "CONFIG_MISSING")
                    self.assertGreater(len(ctx.exception.missing), 0)
                    self.assertEqual(http.call_count, 0, "缺凭据时不得发起任何 HTTP 请求")
                    self.assertEqual(len(smtp.envelopes), 0, "缺凭据时不得发起任何 SMTP 发送")

    def test_validate_config_alone_raises_before_io(self):
        with patch.dict(os.environ, {}, clear=True):
            registry = default_registry()
            for channel_type, ref, settings in CASES:
                with self.subTest(channel_type=channel_type):
                    channel = registry.resolve(channel_type)
                    config = ChannelConfig(
                        name="test", channel_type=channel_type,
                        credential_ref=ref, settings=settings,
                    )
                    with self.assertRaises(ConfigMissingError):
                        channel.validate_config(config)

    def test_partial_credentials_still_raise_and_no_io(self):
        # 企业微信应用只给了 3 个凭据中的 2 个，仍必须整体拒绝
        partial_env = {
            "WECOM_CORP_ID": "corp-partial",
            "WECOM_AGENT_ID": "1000002",
            # 故意缺 WECOM_AGENT_SECRET
        }
        with patch.dict(os.environ, partial_env, clear=True):
            channel = default_registry().resolve(ChannelType.WECOM_APP)
            config = ChannelConfig(
                name="test", channel_type=ChannelType.WECOM_APP,
                credential_ref="WECOM", settings={"touser": "@all"},
            )
            http = FakeHttpTransport()
            with self.assertRaises(ConfigMissingError) as ctx:
                channel.send(MESSAGE, config, http, FakeSmtpTransport())
            self.assertIn("WECOM_AGENT_SECRET", ctx.exception.missing)
            self.assertEqual(http.call_count, 0)

    def test_disabled_channel_raises_instead_of_sending(self):
        with patch.dict(os.environ, {
            "WECOM_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=K",
        }, clear=True):
            channel = default_registry().resolve(ChannelType.WECOM_WEBHOOK)
            config = ChannelConfig(
                name="test", channel_type=ChannelType.WECOM_WEBHOOK,
                credential_ref="WECOM", is_enabled=False,
            )
            http = FakeHttpTransport()
            with self.assertRaises(ChannelDisabledError):
                channel.send(MESSAGE, config, http, FakeSmtpTransport())
            self.assertEqual(http.call_count, 0)

    def test_error_message_is_explicit_about_authorization(self):
        with patch.dict(os.environ, {}, clear=True):
            channel = default_registry().resolve(ChannelType.WECOM_WEBHOOK)
            config = ChannelConfig(
                name="test", channel_type=ChannelType.WECOM_WEBHOOK,
                credential_ref="ABSENT",
            )
            with self.assertRaises(ConfigMissingError) as ctx:
                channel.validate_config(config)
            text = str(ctx.exception)
            self.assertIn("缺少", text)
            self.assertIn("禁止推送", text)


if __name__ == "__main__":
    unittest.main()
