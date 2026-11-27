"""提示词版本、模板渲染与结构化输出 schema 提示（纯标准库）。

提示词全部版本化并写入 ``ai_call_logs.prompt_version`` 与生成来源元数据。
学科策略里的 ``extraction_prompt`` 作为模板覆盖内置默认模板，实现「新增
学科无需改代码」。Unicode（中文/俄语/法语/英语）原生支持。

模板语法：``{variable}`` 替换，``{{`` / ``}}`` 输出字面花括号；strict 模式
下未知变量明确报错（避免静默产出错误提示词）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from .errors import ErrorDetail, StructuredOutputError
from .validation import QUESTION_TYPES

PROMPT_VERSION_EXTRACTION = "kp-extract-v1"
PROMPT_VERSION_GENERATION = "review-item-gen-v1"
PROMPT_VERSION_EVALUATION = "answer-eval-v1"

DEFAULT_EXTRACTION_SYSTEM = (
    "你是学习知识整理助手。请只输出一个 JSON 对象，不要输出任何额外文字或代码块。"
    "把笔记拆解为可独立复习的结构化知识点；学科由调用方给定，原文语言保持不变。"
)
DEFAULT_GENERATION_SYSTEM = (
    "你是复习题编写助手。请只输出一个 JSON 对象，不要输出任何额外文字或代码块。"
    "题目、答案、解析与摘要必须与给定知识点一致，语言与知识点原文一致。"
)

EXTRACTION_SCHEMA_HINT: dict[str, Any] = {
    "type": "object",
    "required": ["knowledge_points"],
    "properties": {
        "knowledge_points": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "body", "summary", "difficulty", "keywords", "tags"],
                "properties": {
                    "title": {"type": "string", "maxLength": 300},
                    "body": {"type": "string"},
                    "summary": {"type": "string"},
                    "difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}

GENERATION_SCHEMA_HINT: dict[str, Any] = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question_type", "question", "answer", "explanation", "summary"],
                "properties": {
                    "question_type": {"enum": sorted(QUESTION_TYPES)},
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "explanation": {"type": "string"},
                    "summary": {"type": "string"},
                    "options": {"type": ["array", "null"], "items": {"type": "string"}},
                },
            },
        }
    },
}

_VAR = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SENTINEL_OPEN = "\ue000{\ue001"
_SENTINEL_CLOSE = "\ue002}\ue003"


def render_template(
    template: str, variables: Mapping[str, Any], *, strict: bool = True
) -> str:
    """渲染 ``{var}``；``{{``/``}}`` 为字面花括号。

    Args:
        template: 模板文本（可为学科策略里的 extraction_prompt）。
        variables: 变量字典，值用 ``str()`` 渲染。
        strict: True 时遇到未提供的变量抛 ``StructuredOutputError``。
    """
    if not isinstance(template, str):
        raise StructuredOutputError("模板必须为字符串")
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            if strict:
                missing.append(name)
                return match.group(0)
            return match.group(0)
        return str(variables[name])

    text = template.replace("{{", _SENTINEL_OPEN).replace("}}", _SENTINEL_CLOSE)
    text = _VAR.sub(replace, text)
    if missing:
        raise StructuredOutputError(
            "提示词模板存在未提供的变量：" + ", ".join(sorted(set(missing))),
            details=[ErrorDetail(name, "missing template variable") for name in sorted(set(missing))],
        )
    return text.replace(_SENTINEL_OPEN, "{").replace(_SENTINEL_CLOSE, "}")


def _strategy_attr(strategy: Any, name: str, default: Any = "") -> Any:
    value = getattr(strategy, name, default)
    return default if value is None else value


def _glossary_block(glossary: Mapping[str, str]) -> str:
    if not glossary:
        return "（无术语表覆盖）"
    return "\n".join(f"- {term}: {definition}" for term, definition in glossary.items())


def build_extraction_prompt(
    strategy: Any,
    *,
    subject_name: str,
    note_title: str,
    note_content: str,
    prompt_version: str = PROMPT_VERSION_EXTRACTION,
    schema_hint: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """构造知识点抽取提示词，返回 ``(system, user)``。

    学科自定义 ``extraction_prompt`` 若提供则作为 user 模板覆盖默认模板；
    其中可使用 ``{subject}`` / ``{glossary}`` / ``{note_title}`` / ``{note_content}``。
    """
    glossary = _strategy_attr(strategy, "glossary", {})
    variables = {
        "subject": subject_name,
        "glossary": _glossary_block(glossary),
        "note_title": note_title,
        "note_content": note_content,
        "prompt_version": prompt_version,
        "schema": json.dumps(
            EXTRACTION_SCHEMA_HINT if schema_hint is None else schema_hint, ensure_ascii=False
        ),
    }
    custom = _strategy_attr(strategy, "extraction_prompt", "")
    if custom:
        user = render_template(custom, variables)
        if "{schema}" not in custom:
            user += "\n请输出符合以下 JSON schema 的 JSON 对象:\n" + variables["schema"]
    else:
        # schema 作为变量注入；若直接拼接 JSON 文本，其中的 }} 会被当成转义花括号。
        user = render_template(
            "学科: {subject}\n提示词版本: {prompt_version}\n术语表:\n{glossary}\n"
            "笔记标题: {note_title}\n笔记原文:\n{note_content}\n"
            "请输出符合以下 JSON schema 的 JSON 对象:\n{schema}",
            variables,
        )
    return DEFAULT_EXTRACTION_SYSTEM, user


def build_generation_prompt(
    strategy: Any,
    *,
    subject_name: str,
    knowledge_title: str,
    knowledge_body: str,
    question_types: list[str],
    count: int,
    prompt_version: str = PROMPT_VERSION_GENERATION,
) -> tuple[str, str]:
    """构造复习题生成提示词，返回 ``(system, user)``。"""
    glossary = _strategy_attr(strategy, "glossary", {})
    system = _strategy_attr(strategy, "system_prompt", "") or DEFAULT_GENERATION_SYSTEM
    variables = {
        "subject": subject_name,
        "glossary": _glossary_block(glossary),
        "knowledge_title": knowledge_title,
        "knowledge_body": knowledge_body,
        "question_types": ", ".join(question_types),
        "count": count,
        "prompt_version": prompt_version,
        "schema": json.dumps(GENERATION_SCHEMA_HINT, ensure_ascii=False),
    }
    user = render_template(
        "学科: {subject}\n提示词版本: {prompt_version}\n术语表:\n{glossary}\n"
        "知识点标题: {knowledge_title}\n知识点正文:\n{knowledge_body}\n"
        "需要题型: {question_types}\n共生成 {count} 道题。\n"
        "请输出符合以下 JSON schema 的 JSON 对象:\n{schema}",
        variables,
    )
    return system, user
