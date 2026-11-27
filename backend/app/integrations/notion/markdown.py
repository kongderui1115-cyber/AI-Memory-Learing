"""Notion blocks → Markdown（纯标准库逻辑，Unicode 原生支持）。

用于 ``raw_notes.content_markdown`` 原文留存：标题、段落、列表、待办、
代码、引用、标注、分割线、表格、子页面等常见块类型转换为可读 Markdown。
不联网、不修改外部内容，多语言文本（中文/俄语/法语/英语）原样保留。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def rich_text_to_markdown(items: Iterable[Mapping[str, Any]]) -> str:
    """把 Notion rich_text 数组转换为 Markdown 行内文本。"""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "equation" or "equation" in item:
            expression = (item.get("equation") or {}).get("expression", "")
            parts.append(f"${expression}$" if expression else "")
            continue
        plain = item.get("plain_text")
        if not isinstance(plain, str):
            plain = (item.get("text") or {}).get("content", "")
        if not plain:
            continue
        text = plain
        annotations = item.get("annotations") or {}
        if annotations.get("code"):
            text = f"`{text}`"
        else:
            if annotations.get("bold"):
                text = f"**{text}**"
            if annotations.get("italic"):
                text = f"*{text}*"
            if annotations.get("strikethrough"):
                text = f"~~{text}~~"
        link = (item.get("text") or {}).get("link") or item.get("href")
        if isinstance(link, Mapping):
            link = link.get("url")
        if link:
            text = f"[{text}]({link})"
        parts.append(text)
    return "".join(parts)


def _rich_text_of(block: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    block_type = str(block.get("type") or "")
    payload = block.get(block_type)
    if isinstance(payload, Mapping):
        rich = payload.get("rich_text")
        if isinstance(rich, list):
            return rich
    return []


def _caption(block: Mapping[str, Any]) -> str:
    payload = block.get(str(block.get("type") or ""))
    if isinstance(payload, Mapping):
        caption = payload.get("caption")
        if isinstance(caption, list):
            return rich_text_to_markdown(caption)
    return ""


def block_to_markdown(block: Mapping[str, Any], *, numbered_index: int = 1) -> str:
    """单个块转换为 Markdown 片段。"""
    if not isinstance(block, Mapping):
        return ""
    block_type = str(block.get("type") or "")
    text = rich_text_to_markdown(_rich_text_of(block))

    if block_type in ("heading_1", "heading_2", "heading_3"):
        level = int(block_type[-1])
        return f"{'#' * level} {text}\n\n"
    if block_type == "paragraph":
        return f"{text}\n\n" if text else "\n"
    if block_type == "bulleted_list_item":
        return f"- {text}\n"
    if block_type == "numbered_list_item":
        return f"{numbered_index}. {text}\n"
    if block_type == "to_do":
        checked = bool((block.get("to_do") or {}).get("checked"))
        return f"- [{'x' if checked else ' '}] {text}\n"
    if block_type == "code":
        payload = block.get("code") or {}
        language = payload.get("language") or ""
        return f"```{language}\n{text}\n```\n\n"
    if block_type == "quote":
        return "\n".join(f"> {line}" for line in text.splitlines()) + "\n\n"
    if block_type == "callout":
        return f"> {text}\n\n"
    if block_type == "divider":
        return "---\n\n"
    if block_type == "toggle":
        return f"<details><summary>{text}</summary>\n\n"
    if block_type in ("child_page", "child_database"):
        title = (block.get(block_type) or {}).get("title") or text
        return f"## {title}\n\n"
    if block_type == "image":
        payload = block.get("image") or {}
        url = ""
        if payload.get("type") == "external":
            url = (payload.get("external") or {}).get("url") or ""
        else:
            url = (payload.get("file") or {}).get("url") or ""
        return f"![{_caption(block)}]({url})\n\n" if url else ""
    if block_type in ("file", "pdf", "video", "audio"):
        return f"[{block_type}: {_caption(block) or text}]\n\n"
    if block_type == "table_row":
        cells = block.get("table_row", {}).get("cells", [])
        return "| " + " | ".join(rich_text_to_markdown(cell) for cell in cells) + " |\n"
    if block_type == "equation":
        expression = (block.get("equation") or {}).get("expression") or ""
        return f"$$\n{expression}\n$$\n\n"
    # 未知块：有文本则保留文本，避免丢失原文；不编造内容。
    return f"{text}\n\n" if text else ""


def blocks_to_markdown(blocks: Iterable[Mapping[str, Any]]) -> str:
    """整页块列表转换为 Markdown；为有序列表维护递增编号。"""
    chunks: list[str] = []
    numbered_index = 0
    previous_was_numbered = False
    for block in blocks:
        block_type = str((block or {}).get("type") or "")
        if block_type == "numbered_list_item":
            numbered_index = numbered_index + 1 if previous_was_numbered else 1
            previous_was_numbered = True
            chunks.append(block_to_markdown(block, numbered_index=numbered_index))
        else:
            previous_was_numbered = False
            chunks.append(block_to_markdown(block))
    result = "".join(chunks).strip()
    return result + "\n" if result else ""
