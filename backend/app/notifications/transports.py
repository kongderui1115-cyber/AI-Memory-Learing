"""外部 I/O 端口与标准库生产实现（NOTIF-03 / NOTIF-04 真实发送路径）。

硬约束（本批次）：
- 不安装依赖、不联网、不调用任何外部通知 API、不发任何真实消息。
- 测试替身只允许隔离 HTTP / SMTP，且必须明确标注；不得把 mock 通过写成真实推送通过。
- 生产实现 UrllibHttpTransport / SmtplibTransport 只有在凭据齐全且 worker 真实运行时
  才会被调用（本批次未执行），它们本身不会主动发起任何请求。
"""

from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

from .errors import ChannelDeliveryError

_SENSITIVE_KEYWORDS = (
    "token", "secret", "password", "passwd", "key", "authorization",
    "webhook", "url", "access_token", "corpsecret", "sign", "credential",
)


def mask(value: Any) -> str:
    """把敏感值打码：URL 走 safe_url 脱敏，长串保留末 4 位便于排查。"""
    text = str(value)
    if text.startswith("http://") or text.startswith("https://"):
        return safe_url(text)
    if len(text) <= 4:
        return "***"
    return f"***{text[-4:]}"


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """按键名脱敏；秘密绝不进入 delivery 元数据。递归处理嵌套 dict。"""
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        lowered = str(key).lower()
        if any(word in lowered for word in _SENSITIVE_KEYWORDS):
            out[key] = mask(value)
        elif isinstance(value, dict):
            out[key] = redact_mapping(value)
        else:
            out[key] = value
    return out


def safe_url(url: str) -> str:
    """用于日志 / 元数据的 URL 脱敏：query 中敏感参数打码、path 中的长 token 段打码。"""
    parsed = urllib.parse.urlsplit(url)
    segments = []
    for seg in parsed.path.split("/"):
        lowered = seg.lower()
        # path 中的长 token 或含敏感词的段（如 Server 酱 /{token}.send）一律打码
        if len(seg) > 24 or any(word in lowered for word in ("token", "secret", "key", "sct", "push")):
            segments.append("***")
        else:
            segments.append(seg)
    path = "/".join(segments)
    if not parsed.query:
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", parsed.fragment))
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    safe_pairs = [
        (key, mask(value) if any(w in key.lower() for w in _SENSITIVE_KEYWORDS) else value)
        for key, value in pairs
    ]
    return urllib.parse.urlunsplit((
        parsed.scheme, parsed.netloc, path,
        urllib.parse.urlencode(safe_pairs), parsed.fragment,
    ))


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        try:
            data = json.loads(self.body)
        except (ValueError, TypeError) as exc:
            raise ChannelDeliveryError(
                "渠道响应不是合法 JSON",
                error_code="EXTERNAL_SERVICE_ERROR",
                retryable=True,
            ) from exc
        if not isinstance(data, dict):
            raise ChannelDeliveryError("渠道响应 JSON 顶层不是对象", retryable=True)
        return data


class HttpTransport(ABC):
    """隔离 HTTP 的端口；测试可注入 FakeHttpTransport（明确标注为测试替身）。"""

    @abstractmethod
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: float = 10.0,
    ) -> HttpResult: ...


@dataclass(frozen=True)
class SmtpEnvelope:
    host: str
    port: int
    user: str
    password: str
    from_addr: str
    to_addrs: list[str]
    subject: str
    body: str
    use_tls: bool = True
    timeout: float = 10.0
    use_ssl: bool = False
    message_id: str | None = None

    def redacted(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "from": self.from_addr,
            "to_count": len(self.to_addrs),
            "subject": self.subject,
            "use_tls": self.use_tls,
            "user": mask(self.user),
            "password": mask(self.password),
        }


@dataclass(frozen=True)
class SmtpResult:
    ok: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = True


class SmtpTransport(ABC):
    """隔离 SMTP 的端口；测试可注入 FakeSmtpTransport（明确标注为测试替身）。"""

    @abstractmethod
    def send(self, envelope: SmtpEnvelope) -> SmtpResult: ...


class UrllibHttpTransport(HttpTransport):
    """标准库真实 HTTP 实现。仅在凭据授权后由 worker 调用；本批次不执行。"""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: float = 10.0,
    ) -> HttpResult:
        data = body.encode("utf-8") if body is not None else None
        req = urllib.request.Request(url=url, data=data, method=method.upper())
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResult(
                    status_code=resp.status,
                    body=resp.read().decode("utf-8", errors="replace"),
                    headers=dict(resp.headers),
                )
        except urllib.error.HTTPError as exc:
            return HttpResult(
                status_code=exc.code,
                body=exc.read().decode("utf-8", errors="replace"),
                headers=dict(exc.headers or {}),
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ChannelDeliveryError(
                f"HTTP 请求失败: {exc}",
                error_code="EXTERNAL_TIMEOUT",
                retryable=True,
            ) from exc


class SmtplibTransport(SmtpTransport):
    """标准库真实 SMTP 实现。仅在凭据授权后由 worker 调用；本批次不执行。"""

    def send(self, envelope: SmtpEnvelope) -> SmtpResult:
        message = EmailMessage()
        message["Subject"] = envelope.subject
        message["From"] = envelope.from_addr
        message["To"] = ", ".join(envelope.to_addrs)
        message.set_content(envelope.body, charset="utf-8")
        if envelope.message_id:
            message["Message-ID"] = envelope.message_id
        try:
            context = ssl.create_default_context()
            connection = (smtplib.SMTP_SSL(envelope.host, envelope.port, timeout=envelope.timeout, context=context)
                if envelope.use_ssl else smtplib.SMTP(envelope.host, envelope.port, timeout=envelope.timeout))
            with connection as client:
                if envelope.use_tls:
                    client.starttls(context=context)
                if envelope.user:
                    client.login(envelope.user, envelope.password)
                client.send_message(message)
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            return SmtpResult(False, error_message=str(exc), retryable=True)
        return SmtpResult(True, provider_message_id=message.get("Message-ID"))
