"""渠道真实发送路径的「请求构造 / 响应解析」测试（NOTIF-03 / NOTIF-04）。

明确标注：这里使用 FakeHttpTransport / FakeSmtpTransport 作为测试替身，
仅隔离 HTTP / SMTP 以断言请求构造与解析逻辑，**不发真实网络请求、不代表真实送达**。
真实渠道联调（NOTIF-07）需用户授权 BLK-03 / BLK-04 后另做，本批次一律标为未验证。
所有 URL / 邮箱均为保留域或官方占位域名，不会触达真实服务。
"""

import json
import os
import sys
import unittest
import urllib.parse
from unittest.mock import patch

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.channels import default_registry  # noqa: E402
from app.notifications.config import ChannelConfig  # noqa: E402
from app.notifications.contract_values import ChannelType  # noqa: E402
from app.notifications.errors import ChannelDeliveryError, ConfigMissingError, NotificationError  # noqa: E402
from app.notifications.ports import RenderedMessage  # noqa: E402

try:
    from .fakes import FakeHttpTransport, FakeSmtpTransport  # noqa: E402
except (ImportError, ValueError):
    from fakes import FakeHttpTransport, FakeSmtpTransport  # noqa: E402


OK_BODY = json.dumps({
    "errcode": 0, "errmsg": "ok",
    "access_token": "AT", "msgid": "MID",
    "code": 0, "message": "success",
    "process_instance_id": "PID",
}, ensure_ascii=False)

MESSAGE = RenderedMessage(
    title="【复习提醒】IRQL 与 DPC",
    body="【答案要点】DISPATCH_LEVEL 禁止缺页异常，故不能访问分页内存。",
)

ENV = {
    "WECOM_CORP_ID": "corp-test",
    "WECOM_AGENT_ID": "1000002",
    "WECOM_AGENT_SECRET": "wecom-secret-ABC",
    "WECOM_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=HOOK-KEY-ABC",
    "WECHAT_APP_ID": "wx-app-id",
    "WECHAT_APP_SECRET": "wx-secret-XYZ",
    "THIRD_PARTY_PUSH_TOKEN": "sct-token-SECRET123",
    "DINGTALK_WEBHOOK_URL": "https://oapi.dingtalk.com/robot/send?access_token=DT-TOKEN-ABC",
    "DINGTALK_WEBHOOK_SECRET": "dt-webhook-SECRET",
    "DINGTALK_APP_KEY": "dt-app-key",
    "DINGTALK_APP_SECRET": "dt-app-SECRET",
    "SMTP_USER": "learner@smtp.example.invalid",
    "SMTP_PASSWORD": "smtp-PASSWORD-SECRET",
    "SMTP_HOST": "smtp.example.invalid",
    "SMTP_FROM": "noreply@example.invalid",
}

REFS = {
    ChannelType.WECOM_APP: "WECOM",
    ChannelType.WECHAT_OFFICIAL_ACCOUNT: "WECHAT",
    ChannelType.THIRD_PARTY_PUSH: "THIRD_PARTY_PUSH",
    ChannelType.WECOM_WEBHOOK: "WECOM",
    ChannelType.DINGTALK_WEBHOOK: "DINGTALK",
    ChannelType.DINGTALK_APP: "DINGTALK",
    ChannelType.SMTP: "SMTP",
}

SETTINGS = {
    ChannelType.WECOM_APP: {"touser": "@all"},
    ChannelType.WECHAT_OFFICIAL_ACCOUNT: {"touser": "OPENID-1", "template_id": "TPL-1"},
    ChannelType.THIRD_PARTY_PUSH: {"provider": "serverchan"},
    ChannelType.WECOM_WEBHOOK: {},
    ChannelType.DINGTALK_WEBHOOK: {},
    ChannelType.DINGTALK_APP: {"agent_id": "123", "userid_list": "user1,user2"},
    ChannelType.SMTP: {"to_addresses": ["learner@example.invalid"]},
}


def _config(channel_type, **overrides):
    base = dict(
        name="test",
        channel_type=channel_type,
        credential_ref=REFS[channel_type],
        settings=dict(SETTINGS[channel_type]),
    )
    base.update(overrides)
    return ChannelConfig(**base)


class ChannelRequestConstructionTest(unittest.TestCase):
    def setUp(self):
        self._patcher = patch.dict(os.environ, ENV, clear=True)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.registry = default_registry()

    def test_wecom_webhook_body_contains_concrete_knowledge(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        result = self.registry.resolve(ChannelType.WECOM_WEBHOOK).send(
            MESSAGE, _config(ChannelType.WECOM_WEBHOOK), http, FakeSmtpTransport()
        )
        self.assertTrue(result.ok)
        self.assertEqual(http.call_count, 1)
        body = http.json_bodies()[0]
        self.assertEqual(body["msgtype"], "text")
        self.assertIn(MESSAGE.title, body["text"]["content"])
        self.assertIn("答案要点", body["text"]["content"])

    def test_wecom_app_two_step_token_then_message(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        result = self.registry.resolve(ChannelType.WECOM_APP).send(
            MESSAGE, _config(ChannelType.WECOM_APP), http, FakeSmtpTransport()
        )
        self.assertTrue(result.ok)
        self.assertEqual(http.call_count, 2)
        self.assertEqual(http.calls[0].method, "GET")
        self.assertIn("gettoken", http.calls[0].url)
        self.assertEqual(http.calls[1].method, "POST")
        self.assertIn("message/send", http.calls[1].url)
        self.assertIn("access_token=", http.calls[1].url)
        payload = http.json_bodies()[0]
        self.assertEqual(payload["agentid"], 1000002)
        self.assertIn("答案要点", payload["text"]["content"])
        self.assertEqual(result.provider_message_id, "MID")
        self.assertNotIn("wecom-secret-ABC", json.dumps(result.response_metadata))

    def test_official_account_template_fields_carry_content(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        result = self.registry.resolve(ChannelType.WECHAT_OFFICIAL_ACCOUNT).send(
            MESSAGE, _config(ChannelType.WECHAT_OFFICIAL_ACCOUNT), http, FakeSmtpTransport()
        )
        self.assertTrue(result.ok)
        self.assertEqual(http.call_count, 2)
        payload = http.json_bodies()[0]
        self.assertEqual(payload["touser"], "OPENID-1")
        self.assertIn("first", payload["data"])
        self.assertIn("keyword1", payload["data"])
        self.assertIn(MESSAGE.title, json.dumps(payload["data"], ensure_ascii=False))
        self.assertNotIn("wx-secret-XYZ", json.dumps(result.response_metadata))

    def test_third_party_push_serverchan_form_and_url_redaction(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        result = self.registry.resolve(ChannelType.THIRD_PARTY_PUSH).send(
            MESSAGE, _config(ChannelType.THIRD_PARTY_PUSH), http, FakeSmtpTransport()
        )
        self.assertTrue(result.ok)
        self.assertEqual(http.call_count, 1)
        self.assertIn("sctapi.ftqq.com", http.calls[0].url)
        form = urllib.parse.parse_qs(http.calls[0].body)
        self.assertEqual(form["title"][0], MESSAGE.title)
        self.assertIn("答案要点", form["desp"][0])
        # path 中的 token 不得出现在脱敏元数据里
        self.assertNotIn("sct-token-SECRET123", json.dumps(result.response_metadata))

    def test_bark_namespaced_key_and_compact_payload_preserve_review_link(self):
        channel = self.registry.resolve(ChannelType.THIRD_PARTY_PUSH)
        config = _config(ChannelType.THIRD_PARTY_PUSH, credential_ref="LEARNER_BARK",
                         settings={"provider": "bark"})
        review_url = "https://example.invalid/app?view=review&task=fixture"
        message = RenderedMessage("复习", "知识内容" * 900, review_url=review_url)
        http = FakeHttpTransport(default_body='{"code":200,"message":"fixture-device-key"}')
        with patch.dict(os.environ, {"LEARNER_BARK_DEVICE_KEY": "fixture-device-key"}):
            result = channel.send(message, config, http, FakeSmtpTransport())
        self.assertEqual(http.call_count, 1)
        self.assertEqual(http.calls[0].url, "https://api.day.app/push")
        payload = http.json_bodies()[0]
        self.assertEqual(payload["device_key"], "fixture-device-key")
        self.assertEqual(payload["url"], review_url)
        self.assertLessEqual(len(payload["body"].encode("utf-8")), 1024)
        self.assertTrue(payload["body"].endswith("…"))
        self.assertTrue(result.response_metadata["provider_accepted"])
        self.assertEqual(result.response_metadata["final_delivery"], "unconfirmed")
        self.assertNotIn("fixture-device-key", str(result))

    def test_bark_rejects_missing_key_custom_endpoint_and_unsafe_link_before_io(self):
        channel = self.registry.resolve(ChannelType.THIRD_PARTY_PUSH)
        http, smtp = FakeHttpTransport(), FakeSmtpTransport()
        config = _config(ChannelType.THIRD_PARTY_PUSH, credential_ref="LEARNER_BARK",
                         settings={"provider": "bark"})
        with patch.dict(os.environ, {"BARK_DEVICE_KEY": "another-user-key"}):
            with self.assertRaises(ConfigMissingError):
                channel.send(MESSAGE, config, http, smtp)
        config.settings["endpoint"] = "https://example.invalid/push"
        with patch.dict(os.environ, {"LEARNER_BARK_DEVICE_KEY": "fixture-device-key"}):
            with self.assertRaises(NotificationError) as error:
                channel.send(MESSAGE, config, http, smtp)
            self.assertEqual(error.exception.code, "VALIDATION_ERROR")
            config.settings.pop("endpoint")
            message = RenderedMessage("复习", "内容", review_url="javascript:alert(1)")
            with self.assertRaises(NotificationError):
                channel.send(message, config, http, smtp)
        self.assertEqual(http.call_count, 0)

    def test_bark_acceptance_requires_explicit_success_and_sanitizes_failures(self):
        channel = self.registry.resolve(ChannelType.THIRD_PARTY_PUSH)
        config = _config(ChannelType.THIRD_PARTY_PUSH, credential_ref="LEARNER_BARK",
                         settings={"provider": "bark"})
        smtp = FakeSmtpTransport()
        with patch.dict(os.environ, {"LEARNER_BARK_DEVICE_KEY": "fixture-device-key"}):
            for status, body, retryable in [
                (429, "fixture-device-key", True),
                (403, "fixture-device-key", False),
                (200, '{"message":"fixture-device-key"}', True),
                (200, '{"code":400,"message":"fixture-device-key"}', False),
            ]:
                with self.subTest(status=status, retryable=retryable):
                    http = FakeHttpTransport(default_status=status, default_body=body)
                    with self.assertRaises(ChannelDeliveryError) as error:
                        channel.send(MESSAGE, config, http, smtp)
                    self.assertEqual(error.exception.retryable, retryable)
                    self.assertNotIn("fixture-device-key", str(error.exception))
                    self.assertNotIn("fixture-device-key", str(error.exception.response_metadata))

    def test_dingtalk_webhook_signed_url_hides_secret_and_sign(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        result = self.registry.resolve(ChannelType.DINGTALK_WEBHOOK).send(
            MESSAGE, _config(ChannelType.DINGTALK_WEBHOOK), http, FakeSmtpTransport()
        )
        self.assertTrue(result.ok)
        url = http.calls[0].url
        self.assertIn("timestamp=", url)
        self.assertIn("sign=", url)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        meta = json.dumps(result.response_metadata)
        self.assertNotIn("dt-webhook-SECRET", meta)
        self.assertNotIn(query["sign"][0], meta)

    def test_dingtalk_app_two_step(self):
        http = FakeHttpTransport(default_body=OK_BODY)
        result = self.registry.resolve(ChannelType.DINGTALK_APP).send(
            MESSAGE, _config(ChannelType.DINGTALK_APP), http, FakeSmtpTransport()
        )
        self.assertTrue(result.ok)
        self.assertEqual(http.call_count, 2)
        payload = http.json_bodies()[0]
        self.assertEqual(payload["agent_id"], "123")
        self.assertEqual(payload["userid_list"], "user1,user2")
        self.assertIn("答案要点", payload["msg"]["text"]["content"])
        self.assertEqual(result.provider_message_id, "PID")

    def test_smtp_envelope_carries_content_and_hides_password(self):
        smtp = FakeSmtpTransport()
        result = self.registry.resolve(ChannelType.SMTP).send(
            MESSAGE, _config(ChannelType.SMTP), FakeHttpTransport(), smtp
        )
        self.assertTrue(result.ok)
        self.assertEqual(len(smtp.envelopes), 1)
        envelope = smtp.envelopes[0]
        self.assertIn(MESSAGE.title, envelope.subject)
        self.assertIn("答案要点", envelope.body)
        self.assertNotIn("smtp-PASSWORD-SECRET", json.dumps(result.request_metadata))

    def test_all_builtin_channels_have_real_send_path(self):
        # 覆盖矩阵：7 种 channel_type 在「已提供凭据」时都能构造出真实发送请求
        # （测试替身隔离 I/O），且正文中都含具体知识点内容。
        for channel_type in ChannelType.ALL:
            with self.subTest(channel_type=channel_type):
                http = FakeHttpTransport(default_body=OK_BODY)
                smtp = FakeSmtpTransport()
                result = self.registry.resolve(channel_type).send(
                    MESSAGE, _config(channel_type), http, smtp
                )
                self.assertTrue(result.ok)
                self.assertGreaterEqual(http.call_count + len(smtp.envelopes), 1)
                all_text = urllib.parse.unquote(" ".join(
                    [call.body or "" for call in http.calls]
                    + [env.body for env in smtp.envelopes]
                ))
                self.assertIn("答案要点", all_text)

    def test_business_error_retryable_classification(self):
        busy = FakeHttpTransport(default_body=json.dumps({"errcode": 45009, "errmsg": "freq limit"}))
        with self.assertRaises(ChannelDeliveryError) as ctx:
            self.registry.resolve(ChannelType.WECOM_WEBHOOK).send(
                MESSAGE, _config(ChannelType.WECOM_WEBHOOK), busy, FakeSmtpTransport()
            )
        self.assertTrue(ctx.exception.retryable)

        bad_arg = FakeHttpTransport(default_body=json.dumps({"errcode": 40003, "errmsg": "invalid openid"}))
        with self.assertRaises(ChannelDeliveryError) as ctx2:
            self.registry.resolve(ChannelType.WECOM_WEBHOOK).send(
                MESSAGE, _config(ChannelType.WECOM_WEBHOOK), bad_arg, FakeSmtpTransport()
            )
        self.assertFalse(ctx2.exception.retryable)

    def test_http_status_classification(self):
        for status, expected in ((503, True), (400, False)):
            with self.subTest(status=status):
                http = FakeHttpTransport(default_status=status, default_body='{"errcode":-1}')
                with self.assertRaises(ChannelDeliveryError) as ctx:
                    self.registry.resolve(ChannelType.WECOM_WEBHOOK).send(
                        MESSAGE, _config(ChannelType.WECOM_WEBHOOK), http, FakeSmtpTransport()
                    )
                self.assertEqual(ctx.exception.retryable, expected)


if __name__ == "__main__":
    unittest.main()
