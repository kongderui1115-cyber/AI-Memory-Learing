"""NOTIF-03 微信优先：WechatChannel 合规适配器族（FR-07 路径 A/B/C/D）。

现实约束（必须如实告知用户）：个人微信没有官方开放的主动推送 API，
本模块不实现任何逆向 / 非官方协议，也不返回「假推送成功」。
4 种实现均需用户选择并提供凭据；未配置任何凭据时 send() 抛 ConfigMissingError。

- wecom_app                A 企业微信应用消息（官方，稳定，可推送到微信）
- wechat_official_account  B 微信服务号模板/订阅消息（需已认证服务号）
- third_party_push         C Server 酱 / PushPlus（需用户提供 Token）
- wecom_webhook            D 企业微信群机器人 Webhook

wecom_app / wecom_webhook 同时也是 FR-08「企业微信」渠道的真实发送路径。
所有 HTTP 调用都经注入的 HttpTransport（测试用替身明确隔离，本批次不发真实请求）。
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from ..config import ChannelConfig
from ..contract_values import ChannelType
from ..errors import ChannelDeliveryError
from ..ports import RenderedMessage, SendResult
from ..template import char_sizer, truncate
from ..transports import HttpTransport, SmtpTransport, redact_mapping, safe_url
from .bark import BarkChannel
from .base import BaseChannel

_WECHAT_FIELD_LIMIT = 20   # 微信模板/订阅消息 thing 字段常见字符上限
_MAX_TEMPLATE_FIELDS = 5


def _clip(text: str, limit: int) -> str:
    return truncate(text, limit, char_sizer)


def _field_chunks(text: str) -> list[str]:
    return [
        text[i:i + _WECHAT_FIELD_LIMIT]
        for i in range(0, len(text), _WECHAT_FIELD_LIMIT)
    ][:_MAX_TEMPLATE_FIELDS]


class WecomAppChannel(BaseChannel):
    """A：企业微信应用消息（官方、稳定，可推送到微信）。同时是 FR-08 企业微信路径。"""

    channel_type = ChannelType.WECOM_APP
    max_length = 2048            # 企业微信 text.content 上限（字节）
    length_unit = "byte"
    credential_spec = (
        ("corp_id", "WECOM_CORP_ID"),
        ("agent_id", "WECOM_AGENT_ID"),
        ("agent_secret", "WECOM_AGENT_SECRET"),
    )

    def _send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        creds = self.creds(config)
        touser = config.setting("touser", "@all")
        token_url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken?" + urllib.parse.urlencode({
            "corpid": creds["corp_id"],
            "corpsecret": creds["agent_secret"],
        })
        token_data = self._get_json(http, token_url)
        self._biz_ok(token_data, retryable_codes=(-1, 40001, 42001))
        access_token = token_data.get("access_token")
        if not access_token:
            raise ChannelDeliveryError(
                "企业微信未返回 access_token",
                retryable=False,
                response_metadata=redact_mapping(dict(token_data)),
            )

        send_url = "https://qyapi.weixin.qq.com/cgi-bin/message/send?" + urllib.parse.urlencode(
            {"access_token": access_token}
        )
        try:
            agentid: Any = int(creds["agent_id"])
        except ValueError:
            agentid = creds["agent_id"]
        payload = {
            "touser": touser,
            "msgtype": "text",
            "agentid": agentid,
            "text": {"content": message.full_text()},
            "safe": 0,
        }
        data = self._post_json(http, send_url, payload)
        self._biz_ok(data, retryable_codes=(-1, 45009, 45047))
        return SendResult(
            ok=True,
            provider_message_id=str(data["msgid"]) if data.get("msgid") else None,
            request_metadata=self._base_request_meta(config, message),
            response_metadata=redact_mapping({
                "errcode": data.get("errcode"),
                "errmsg": data.get("errmsg"),
                "token_url": safe_url(token_url),
                "send_url": safe_url(send_url),
            }),
        )


class WecomWebhookChannel(BaseChannel):
    """D：企业微信群机器人 Webhook。同时是 FR-08 企业微信路径。"""

    channel_type = ChannelType.WECOM_WEBHOOK
    max_length = 2048
    length_unit = "byte"
    credential_spec = (("webhook_url", "WECOM_WEBHOOK_URL"),)

    def _send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        creds = self.creds(config)
        url = creds["webhook_url"]
        payload = {"msgtype": "text", "text": {"content": message.full_text()}}
        data = self._post_json(http, url, payload)
        self._biz_ok(data, retryable_codes=(-1, 45009))
        return SendResult(
            ok=True,
            provider_message_id=None,
            request_metadata=self._base_request_meta(config, message),
            response_metadata=redact_mapping({
                "errcode": data.get("errcode"),
                "errmsg": data.get("errmsg"),
                "url": safe_url(url),
            }),
        )


class WechatOfficialAccountChannel(BaseChannel):
    """B：微信服务号模板 / 订阅消息（需已认证服务号）。

    模板消息字段长度受微信限制，因此把渲染后的具体知识点正文按 20 字符分片写入
    keyword1..keyword5，first 放标题，复习入口放 url/remark。
    字段名与数量需与用户实际申请的模板一致 —— 该项待授权联调时校准（见交付说明）。
    """

    channel_type = ChannelType.WECHAT_OFFICIAL_ACCOUNT
    max_length = 100             # 5 个字段 x 20 字符，保证单条可完整承载
    length_unit = "char"
    credential_spec = (
        ("app_id", "WECHAT_APP_ID"),
        ("app_secret", "WECHAT_APP_SECRET"),
    )
    settings_spec = ("touser", "template_id")

    def _send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        creds = self.creds(config)
        touser = config.setting("touser")
        template_id = config.setting("template_id")
        message_type = config.setting("message_type", "template")
        review_url = config.setting("review_url", "")

        token_url = "https://api.weixin.qq.com/cgi-bin/token?" + urllib.parse.urlencode({
            "grant_type": "client_credential",
            "appid": creds["app_id"],
            "secret": creds["app_secret"],
        })
        token_data = self._get_json(http, token_url)
        self._biz_ok(token_data, retryable_codes=(-1, 40001, 42001))
        access_token = token_data.get("access_token")
        if not access_token:
            raise ChannelDeliveryError(
                "微信服务号未返回 access_token",
                retryable=False,
                response_metadata=redact_mapping(dict(token_data)),
            )

        chunks = _field_chunks(message.body)
        if message_type == "subscribe":
            endpoint = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"
            data_payload: dict[str, Any] = {"thing1": {"value": _clip(message.title, 20)}}
            for index, chunk in enumerate(chunks[:2], start=2):
                data_payload[f"thing{index}"] = {"value": chunk}
            payload = {
                "touser": touser,
                "template_id": template_id,
                "page": review_url,
                "data": data_payload,
            }
        else:
            endpoint = "https://api.weixin.qq.com/cgi-bin/message/template/send"
            data_payload = {"first": {"value": _clip(f"复习提醒：{message.title}", 50)}}
            for index, chunk in enumerate(chunks, start=1):
                data_payload[f"keyword{index}"] = {"value": chunk}
            data_payload["remark"] = {
                "value": _clip("请进入下方链接完成本次复习：" + review_url, 50)
            }
            payload = {
                "touser": touser,
                "template_id": template_id,
                "url": review_url,
                "data": data_payload,
            }

        send_url = endpoint + "?" + urllib.parse.urlencode({"access_token": access_token})
        data = self._post_json(http, send_url, payload)
        self._biz_ok(data, retryable_codes=(-1, 40001, 45009))
        return SendResult(
            ok=True,
            provider_message_id=str(data["msgid"]) if data.get("msgid") else None,
            request_metadata=self._base_request_meta(config, message),
            response_metadata=redact_mapping({
                "errcode": data.get("errcode"),
                "errmsg": data.get("errmsg"),
                "message_type": message_type,
                "token_url": safe_url(token_url),
                "send_url": safe_url(send_url),
            }),
        )


class ThirdPartyPushChannel(BaseChannel):
    """第三方推送（Server 酱 / PushPlus / Bark）。"""

    channel_type = ChannelType.THIRD_PARTY_PUSH
    max_length = 30000
    length_unit = "char"
    credential_spec = (("token", "THIRD_PARTY_PUSH_TOKEN"),)

    def validate_config(self, config: ChannelConfig) -> None:
        if config.setting("provider") == "bark":
            BarkChannel().validate_config(config)
        else:
            super().validate_config(config)

    def send(self, message, config, http, smtp):
        if config.setting("provider") == "bark":
            return BarkChannel().send(message, config, http, smtp)
        return super().send(message, config, http, smtp)

    def _send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        creds = self.creds(config)
        token = creds["token"]
        provider = config.setting("provider", "serverchan")
        title, body = message.title, message.body

        if provider == "pushplus":
            url = "https://www.pushplus.plus/send"
            payload = {
                "token": token,
                "title": title,
                "content": body,
                "template": "txt",
            }
            data = self._post_json(http, url, payload)
            self._biz_ok(data, ok_field="code", ok_values=(200,), retryable_codes=(-1, 999))
            provider_message_id = str(data["data"]) if data.get("data") else None
        else:
            # Server 酱：token 位于 URL path，safe_url() 会把长 token 段打码
            url = f"https://sctapi.ftqq.com/{urllib.parse.quote(token, safe='')}.send"
            form = urllib.parse.urlencode({"title": title, "desp": body})
            result = http.request(
                "POST",
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=form,
                timeout=self.request_timeout,
            )
            data = self._http_ok(result, url)
            self._biz_ok(data, ok_field="code", ok_values=(0,), retryable_codes=(-1,))
            provider_message_id = None

        return SendResult(
            ok=True,
            provider_message_id=provider_message_id,
            request_metadata=self._base_request_meta(config, message),
            response_metadata=redact_mapping({
                "provider": provider,
                "code": data.get("code"),
                "message": data.get("message") or data.get("msg"),
                "url": safe_url(url),
            }),
        )
