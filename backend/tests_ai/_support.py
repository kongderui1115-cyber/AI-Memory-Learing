"""测试支撑工具（本文件不匹配 ``test*.py``，不会被 unittest discover 收集）。

包含两类内容，务必区分：

1. **真实逻辑校验工具**（非 mock）：用标准库 ``ast`` 解析冻结契约文件
   ``app/contracts/enums.py`` / ``models.py``，验证本模块常量与字段零偏差。
   这些测试读取的是 Chief Architect 独占、共享只读的真实契约文件。

2. **测试替身（MOCK）**：``FakeTransport`` / ``FakeNotionTransport`` /
   ``ai_success_response`` 等仅用于**隔离外部 HTTP**（Notion / DeepSeek /
   OpenAI 一律不真实调用）。它们不联网、不代表外部联调通过、不作为
   集成完成的证据；凡使用它们的测试均在 docstring 中显式标注 MOCK。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from app.ai.ports import HttpResponse

BACKEND = Path(__file__).resolve().parents[1]
CONTRACTS = BACKEND / "app" / "contracts"
ROOT = BACKEND.parent


# ---- 真实逻辑：契约文件 ast 解析 -------------------------------------------
def contract_enum_values() -> dict[str, set[str]]:
    """返回 ``{枚举类名: {字符串值}}``，来自真实 enums.py。"""
    tree = ast.parse((CONTRACTS / "enums.py").read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        values: set[str] = set()
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                values.add(stmt.value.value)
        if values:
            result[node.name] = values
    return result


def contract_model_fields(class_name: str) -> set[str]:
    """返回指定契约类体内声明的注解字段名，来自真实 models.py。"""
    tree = ast.parse((CONTRACTS / "models.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields: set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.add(stmt.target.id)
            return fields
    raise KeyError(f"contracts/models.py 中未找到类 {class_name}")


def read_api_contract() -> str:
    return (ROOT / "API_CONTRACTS.md").read_text(encoding="utf-8")


def read_database_schema() -> str:
    return (ROOT / "DATABASE_SCHEMA.md").read_text(encoding="utf-8")


# ---- MOCK：仅隔离外部 HTTP，绝不联网 ----------------------------------------
class FakeTransport:
    """MOCK：AI Provider 的 HTTP 传输替身（app.ai.ports.Transport）。

    按预置顺序返回响应或抛出预置异常；记录每次调用以便断言请求构造。
    不发起任何网络请求，不代表外部服务联调通过。
    """

    def __init__(
        self,
        responses: list[HttpResponse] | None = None,
        *,
        raise_exc: BaseException | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": bytes(body),
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        if not self.responses:
            raise AssertionError("MOCK FakeTransport 未预置响应，却发起了调用")
        return self.responses.pop(0)


class FakeNotionTransport:
    """MOCK：Notion 的 HTTP 传输替身（app.integrations.notion.client.NotionTransport）。"""

    def __init__(
        self,
        responses: list[HttpResponse] | None = None,
        *,
        raise_exc: BaseException | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": bytes(body) if body else None,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        if not self.responses:
            raise AssertionError("MOCK FakeNotionTransport 未预置响应，却发起了调用")
        return self.responses.pop(0)


def ai_success_response(
    payload: dict[str, Any],
    *,
    input_tokens: int = 11,
    output_tokens: int = 7,
    model: str = "gpt-4o-mini",
) -> HttpResponse:
    """MOCK：构造一个 OpenAI 协议风格的成功响应（不联网）。"""
    raw = {
        "id": "chatcmpl-mock",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }
    return HttpResponse(200, json.dumps(raw, ensure_ascii=False).encode("utf-8"))


def http_error_response(status: int, message: str = "mock error") -> HttpResponse:
    """MOCK：构造一个外部错误响应（不联网）。"""
    return HttpResponse(
        status, json.dumps({"error": {"message": message}}).encode("utf-8")
    )


def notion_query_response(
    pages: list[dict[str, Any]],
    *,
    next_cursor: str | None = None,
    has_more: bool = False,
) -> HttpResponse:
    """MOCK：构造 Notion database 查询响应（不联网）。"""
    raw = {
        "object": "list",
        "results": pages,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "type": "page_or_database",
    }
    return HttpResponse(200, json.dumps(raw, ensure_ascii=False).encode("utf-8"))
