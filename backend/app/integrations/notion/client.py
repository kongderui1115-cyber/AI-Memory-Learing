"""Notion API 真实 HTTP 路径与响应解析（AI-02 / FR-01）。

- ``assert_notion_token`` 是硬约束落点：未授权 Token 直接抛
  ``CONFIG_MISSING``，只保留真实路径，绝不伪造同步结果。
- ``UrllibNotionTransport`` 使用标准库 urllib 发起真实请求；仅在 Token
  存在时才会被调用。本模块自身不主动联网、不产生费用。
- ``NotionTransport`` 可注入：单元测试用 FakeTransport 仅隔离外部 HTTP，
  明确标注为测试替身，不代表外部联调通过。
- 响应解析与标题/版本提取均为纯标准库函数，可独立单测。
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.ai.errors import (
    AIIntegrationError,
    ConfigMissingError,
    ErrorDetail,
    ProviderResponseError,
    ProviderTimeoutError,
    error_from_http_status,
)
from app.ai.ports import HttpResponse
from app.outbound_http import open_authenticated
from .markdown import blocks_to_markdown
from .models import NotionPage

NOTION_API_BASE = "https://api.notion.com/v1"
DEFAULT_API_VERSION = "2022-06-28"


class NotionHTTPError(AIIntegrationError):
    """Expose status and retry timing without retaining the upstream response body."""

    def __init__(self, response: HttpResponse) -> None:
        self.status_code = response.status_code
        message = f"Notion API 返回 HTTP {self.status_code}"
        mapped = error_from_http_status(
            429 if self.status_code == 529 else self.status_code, message, notion=True
        )
        super().__init__(message, error_code=mapped.code)
        self.retryable = mapped.retryable
        self.retry_after_seconds = 0
        if self.status_code in {429, 529}:
            value = next(
                (v for k, v in response.headers.items() if k.lower() == "retry-after"), ""
            ).strip()
            if value.isdecimal():
                # Bound integer parsing and the persisted deadline for invalid upstream values.
                self.retry_after_seconds = (
                    min(int(value), 604800) if len(value) <= 6 else 604800
                )


def assert_notion_token(token: str | None) -> str:
    """未配置 Notion Token 时明确报错（BLK-01 待授权），不返回假数据。"""
    value = (token or "").strip()
    if not value:
        raise ConfigMissingError(
            "Notion Integration Token 未配置（BLK-01 待用户授权）；"
            "只提供真实同步路径，拒绝伪造同步结果。",
            details=[ErrorDetail("NOTION_API_TOKEN", "missing or empty")],
        )
    return value


class NotionTransport(ABC):
    """可注入的 Notion HTTP 传输端口。"""

    @abstractmethod
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        raise NotImplementedError


class UrllibNotionTransport(NotionTransport):
    """基于标准库 urllib 的真实 Notion HTTP 传输。"""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with open_authenticated(request, timeout=timeout_seconds) as response:
                return HttpResponse(
                    status_code=response.status,
                    body=response.read(),
                    headers=dict(response.headers),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status_code=exc.code,
                body=exc.read(),
                headers=dict(exc.headers) if exc.headers else {},
            )
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise ProviderTimeoutError(
                f"Notion API 连接/读取超时或网络不可达（timeout={timeout_seconds}s）: {exc}"
            ) from exc


@dataclass(frozen=True)
class ParsedQueryResult:
    """一次 database 查询的解析结果。"""

    pages: list[NotionPage] = field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


def extract_title(properties: Mapping[str, Any]) -> str:
    """从 Notion properties 中提取 title 类型属性的纯文本（Unicode 保留）。"""
    for prop in properties.values():
        if not isinstance(prop, Mapping):
            continue
        if prop.get("type") == "title":
            items = prop.get("title") or []
            return "".join(
                (item.get("plain_text") or (item.get("text") or {}).get("content") or "")
                for item in items
                if isinstance(item, Mapping)
            )
    return ""


def external_version_for_page(page: Mapping[str, Any]) -> str:
    """外部版本号：以 Notion ``last_edited_time`` 作为页面版本。

    契约 UQ ``(data_source_id, external_page_id, external_version)`` 用此值
    保证同一页面同一版本重复同步不产生重复原文。
    """
    return str(page.get("last_edited_time") or "")


def parse_query_response(
    payload: Mapping[str, Any], *, include_archived: bool = False
) -> ParsedQueryResult:
    """解析 Notion ``/databases/{id}/query`` 响应（纯逻辑）。"""
    if not isinstance(payload, Mapping):
        raise ProviderResponseError("Notion 查询响应顶层必须为对象")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ProviderResponseError("Notion 查询响应缺少 results 数组")
    pages: list[NotionPage] = []
    for raw in results:
        if not isinstance(raw, Mapping):
            continue
        if raw.get("object") not in (None, "page"):
            continue
        archived = any(raw.get(flag) is True for flag in ("archived", "in_trash", "is_archived"))
        if archived and not include_archived:
            continue
        page_id = str(raw.get("id") or "")
        if not page_id:
            continue
        properties = raw.get("properties") if isinstance(raw.get("properties"), Mapping) else {}
        version = external_version_for_page(raw)
        pages.append(
            NotionPage(
                external_page_id=page_id,
                external_version=version + ":archived" if version and archived else version,
                last_edited_time=str(raw.get("last_edited_time") or ""),
                title=extract_title(properties),
                source_url=str(raw.get("url") or ""),
                properties=dict(properties),
                metadata={
                    "created_time": raw.get("created_time"),
                    "object": raw.get("object"),
                    "source_archived": archived,
                    "in_trash": raw.get("in_trash") is True,
                },
                has_children=bool(raw.get("has_children")),
                is_archived=archived,
            )
        )
    next_cursor = payload.get("next_cursor")
    return ParsedQueryResult(
        pages=pages,
        next_cursor=next_cursor if isinstance(next_cursor, str) and next_cursor else None,
        has_more=bool(payload.get("has_more")),
    )


def parse_blocks_response(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """解析 Notion ``/blocks/{id}/children`` 响应（纯逻辑）。"""
    if not isinstance(payload, Mapping):
        raise ProviderResponseError("Notion 块响应顶层必须为对象")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ProviderResponseError("Notion 块响应缺少 results 数组")
    return [block for block in results if isinstance(block, Mapping)]


class NotionClient:
    """Notion 数据源客户端：真实路径 + 缺 Token 明确报错。"""

    def __init__(
        self,
        *,
        token: str | None,
        api_version: str = DEFAULT_API_VERSION,
        transport: NotionTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        # 构造即校验：未授权时对象根本无法创建，杜绝伪造同步结果。
        self._token = assert_notion_token(token)
        self.api_version = api_version or DEFAULT_API_VERSION
        self._transport: NotionTransport = transport or UrllibNotionTransport()
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": self.api_version,
            "Content-Type": "application/json",
        }

    def _request_json(
        self, method: str, url: str, body: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        response = self._transport.request(
            method, url, self._headers(), payload, self.timeout_seconds
        )
        if not (200 <= response.status_code < 300):
            raise NotionHTTPError(response)
        try:
            parsed = response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderResponseError("Notion API 响应不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise ProviderResponseError("Notion API 响应顶层必须为对象")
        return parsed

    def query_database_body(
        self,
        *,
        watermark: str | None = None,
        start_cursor: str | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """构造增量查询请求体（纯逻辑，基于 ``last_edited_time`` 游标）。"""
        if not (1 <= page_size <= 100):
            raise ValueError("page_size 必须处于 1..100（Notion API 限制）")
        body: dict[str, Any] = {
            "page_size": page_size,
            "sorts": [{"timestamp": "last_edited_time", "direction": "ascending"}],
        }
        if watermark:
            body["filter"] = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"after": watermark},
            }
        if start_cursor:
            body["start_cursor"] = start_cursor
        return body

    def query_database(
        self,
        database_id: str,
        *,
        watermark: str | None = None,
        start_cursor: str | None = None,
        page_size: int = 100,
    ) -> ParsedQueryResult:
        """真实拉取一页 database 数据（仅在 Token 授权后才会被调用）。"""
        if not (database_id or "").strip():
            raise ConfigMissingError(
                "Notion Database ID 未配置（BLK-01 待授权）",
                details=[ErrorDetail("NOTION_DATABASE_IDS", "missing")],
            )
        body = self.query_database_body(
            watermark=watermark, start_cursor=start_cursor, page_size=page_size
        )
        url = f"{NOTION_API_BASE}/databases/{database_id}/query"
        return parse_query_response(self._request_json("POST", url, body))

    def retrieve_block_children(
        self, block_id: str, *, start_cursor: str | None = None
    ) -> list[dict[str, Any]]:
        """真实拉取一个块的子块（用于原文 Markdown 还原）。"""
        url = f"{NOTION_API_BASE}/blocks/{block_id}/children?page_size=100"
        if start_cursor:
            url += f"&start_cursor={start_cursor}"
        return parse_blocks_response(self._request_json("GET", url, None))

    def fetch_page_markdown(self, page_id: str) -> str:
        """递归拉取整页块并转 Markdown（真实路径，原文留存）。"""
        blocks = self.retrieve_block_children(page_id)
        expanded: list[dict[str, Any]] = []
        for block in blocks:
            expanded.append(block)
            if block.get("has_children"):
                expanded.extend(self.retrieve_block_children(str(block.get("id") or "")))
        return blocks_to_markdown(expanded)
