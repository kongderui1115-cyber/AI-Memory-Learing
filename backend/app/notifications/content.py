"""具体知识点内容模型（FR-07 核心）。

FR-07 硬要求：推送正文必须是「标题 + 摘要/问题 + 答案要点 + 复习入口」，
绝不能是「您有 N 条待复习」的空通知。本模块提供：
- KnowledgeContent：承载具体内容的数据对象；
- build_context()：把内容展开为模板变量；
- assert_concrete() + validate_rendered_content()：两道防线，确保空通知无法进入发送队列。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import EmptyContentError

#: 明显的「空通知」话术；出现在标题且无其它具体内容时直接拒绝。
_EMPTY_NOTICE_RE = re.compile(
    r"(您有|你有)\s*\d+\s*(条|个).*(待复习|待处理|待办)|待复习数量|review\s*count",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class KnowledgeContent:
    """一条待复习知识点的完整内容（字段来自 knowledge_points / review_items / 复习入口）。"""

    title: str
    summary: str
    question: str
    answer_points: str
    review_url: str
    explanation: str = ""
    subject: str = ""
    knowledge_point_id: str | None = None
    task_id: str | None = None
    review_item_id: str | None = None


#: 默认模板：显式包含标题、学科、摘要、问题、答案要点、解析与复习入口。
#: 不含「您有 N 条待复习」式空话术。
DEFAULT_TITLE_TEMPLATE = "【复习提醒】{title}"
DEFAULT_BODY_TEMPLATE = (
    "【知识点】{title}\n"
    "【学科】{subject}\n"
    "【摘要】{summary}\n"
    "【复习问题】{question}\n"
    "【答案要点】{answer_points}\n"
    "{explanation_line}"
    "【复习入口】{review_url}"
)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def assert_concrete(content: KnowledgeContent) -> None:
    """校验内容足够具体，拒绝空通知（FR-07 第一道防线）。"""
    title = _clean(content.title)
    summary = _clean(content.summary)
    question = _clean(content.question)
    answer = _clean(content.answer_points)
    entry = _clean(content.review_url)

    if not title:
        raise EmptyContentError("知识点标题为空")
    if _EMPTY_NOTICE_RE.search(title) and not (summary or question or answer):
        raise EmptyContentError("标题为空通知话术且无任何具体知识点内容")
    if not (summary or question):
        raise EmptyContentError("摘要与复习问题均为空（至少其一必须提供）")
    if not answer:
        raise EmptyContentError("答案要点为空")
    if not entry:
        raise EmptyContentError("复习入口为空")
    # 至少有一块「具体知识点」正文具备实质长度，防止用极短占位符糊弄。
    concrete_blocks = [block for block in (summary, question, answer) if len(block) >= 4]
    if not concrete_blocks:
        raise EmptyContentError("摘要/问题/答案要点均为极短占位内容，不构成具体知识点")


def build_context(content: KnowledgeContent) -> dict[str, str]:
    """把 KnowledgeContent 展开为模板可用变量（含派生变量）。"""
    explanation = _clean(content.explanation)
    return {
        "title": _clean(content.title),
        "subject": _clean(content.subject) or "未分类",
        "summary": _clean(content.summary) or "（本条无摘要，见复习问题）",
        "question": _clean(content.question) or "（本条无提问，见摘要）",
        "answer_points": _clean(content.answer_points),
        "explanation": explanation,
        "explanation_line": f"【解析】{explanation}\n" if explanation else "",
        "review_url": _clean(content.review_url),
        "review_entry": _clean(content.review_url),
        "knowledge_point_id": content.knowledge_point_id or "",
        "task_id": content.task_id or "",
        "review_item_id": content.review_item_id or "",
    }


def validate_rendered_content(rendered_body: str, content: KnowledgeContent) -> None:
    """校验渲染结果真的包含具体知识点文本（FR-07 第二道防线）。

    即便模板被改坏（漏掉 answer_points 等），也能在入队前拦截，
    确保发出去的正文不是「您有 N 条待复习」。
    """
    if _EMPTY_NOTICE_RE.search(rendered_body) and "【答案要点】" not in rendered_body:
        raise EmptyContentError("渲染正文疑似空通知话术且未包含答案要点")

    title = _clean(content.title)
    answer = _clean(content.answer_points)
    summary = _clean(content.summary)
    question = _clean(content.question)
    entry = _clean(content.review_url)

    if title and title not in rendered_body:
        raise EmptyContentError("渲染正文缺少知识点标题")
    if answer and answer not in rendered_body:
        raise EmptyContentError("渲染正文缺少答案要点")
    if not any(block and block in rendered_body for block in (summary, question)):
        raise EmptyContentError("渲染正文缺少摘要或复习问题")
    if entry and entry not in rendered_body:
        raise EmptyContentError("渲染正文缺少复习入口")
