"""通知模板变量渲染 + 按渠道长度限制自适应裁剪/分段（NOTIF-02 / FR-07、FR-08）。

- 变量渲染基于标准库 string.Formatter，严格模式（缺变量报错，不静默留下 {placeholder}）。
- 长度计量支持「字符」与「UTF-8 字节」两种：企业微信/钉钉按字节限制，
  且按字符累加，绝不切断多字节汉字（Unicode 安全，FR-10 多语言）。
- 超限策略：segment（分段成多条）或 truncate（单条裁剪加省略号）。
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Callable

from .errors import TemplateRenderError
from .ports import RenderedMessage

Sizer = Callable[[str], int]

_BREAK_CHARS = frozenset("\n\r\t 。！？；，、：,.!?;:）)】]》〉")


def char_sizer(text: str) -> int:
    return len(text)


def byte_sizer(text: str) -> int:
    return len(text.encode("utf-8"))


def get_sizer(unit: str) -> Sizer:
    if unit == "char":
        return char_sizer
    if unit == "byte":
        return byte_sizer
    raise ValueError(f"未知长度计量单位: {unit!r}（应为 'char' 或 'byte'）")


def _template_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.add(field_name.split(".")[0].split("[")[0])
    return fields


def _validate_context(template: str, context: dict[str, str]) -> None:
    missing = sorted(_template_fields(template) - set(context))
    if missing:
        raise TemplateRenderError(f"模板引用了未提供的变量: {missing}")


@dataclass
class TemplateRenderer:
    """按 title_template / body_template 渲染并自适应渠道长度。"""

    title_template: str
    body_template: str
    max_length: int | None = None
    length_unit: str = "char"
    adaptive_mode: str = "segment"   # "segment" | "truncate" | "none"
    part_marker: bool = True

    def __post_init__(self) -> None:
        if self.max_length is not None and self.max_length < 1:
            raise ValueError("max_length 必须 >= 1")
        if self.adaptive_mode not in ("segment", "truncate", "none"):
            raise ValueError("adaptive_mode 必须是 segment / truncate / none")
        self._sizer = get_sizer(self.length_unit)

    def render(self, context: dict[str, str]) -> RenderedMessage:
        """变量渲染（严格），返回未分段的单条消息。"""
        for name, tpl in (("title", self.title_template), ("body", self.body_template)):
            try:
                _validate_context(tpl, context)
            except TemplateRenderError as exc:
                raise TemplateRenderError(f"{name}模板: {exc}") from exc
        try:
            title = Formatter().vformat(self.title_template, (), context)
            body = Formatter().vformat(self.body_template, (), context)
        except (KeyError, IndexError, ValueError) as exc:
            raise TemplateRenderError(f"模板渲染失败: {exc}") from exc
        return RenderedMessage(title=title, body=body)

    def adapt(self, rendered: RenderedMessage) -> list[RenderedMessage]:
        """按 max_length 对正文做裁剪/分段；标题随每条消息一起发送。

        标题不参与长度裁剪（渠道发送时以 title + body 组装），保证每条分段消息
        都带有知识点标题，符合 FR-07「具体内容」要求。
        """
        if self.max_length is None or self.adaptive_mode == "none":
            return [rendered]
        if self._sizer(rendered.body) <= self.max_length:
            return [rendered]
        if self.adaptive_mode == "truncate":
            body = truncate(rendered.body, self.max_length, self._sizer)
            return [RenderedMessage(rendered.title, body, 1, 1)]
        segments = split_segments(
            rendered.body, self.max_length, self._sizer, add_marker=self.part_marker
        )
        total = len(segments)
        return [
            RenderedMessage(rendered.title, seg, i, total)
            for i, seg in enumerate(segments, 1)
        ]


def truncate(text: str, max_length: int, sizer: Sizer, ellipsis: str = "…") -> str:
    """安全截断到 max_length；按字符累加，字节模式下不会切断多字节字符。"""
    if sizer(text) <= max_length:
        return text
    budget = max(0, max_length - sizer(ellipsis))
    out: list[str] = []
    used = 0
    for char in text:
        cost = sizer(char)
        if used + cost > budget:
            break
        out.append(char)
        used += cost
    return "".join(out) + ellipsis


def split_segments(
    text: str,
    max_length: int,
    sizer: Sizer,
    *,
    add_marker: bool = True,
    marker_reserve: int | None = None,
) -> list[str]:
    """把 text 切成每段（含段号标记后）长度 <= max_length 的连续段。

    按字符累加 sizer，UTF-8 字节模式下也不会切断汉字。优先在换行/空格/标点处
    断开，保证可读。单段时不加段号标记（无必要）。
    """
    if max_length < 1:
        raise ValueError("max_length 必须 >= 1")
    if sizer(text) <= max_length:
        return [text]

    if marker_reserve is None:
        marker_reserve = sizer("(99/99)\n")  # 保守预留段号宽度
    budget = max(1, max_length - (marker_reserve if add_marker else 0))

    raw = _greedy_split(text, budget, sizer)
    total = len(raw)
    result: list[str] = []
    for index, segment in enumerate(raw, 1):
        marker = f"({index}/{total})\n" if add_marker else ""
        # 预留是保守值；仍做一次兜底校验，必要时回退字符，确保不超限
        while segment and sizer(marker) + sizer(segment) > max_length:
            segment = segment[:-1]
        result.append(marker + segment)
    return result


def _greedy_split(text: str, budget: int, sizer: Sizer) -> list[str]:
    units = [(char, sizer(char)) for char in text]
    count = len(units)
    parts: list[str] = []
    i = 0
    while i < count:
        used = 0
        j = i
        while j < count and used + units[j][1] <= budget:
            used += units[j][1]
            j += 1
        if j < count:
            # 回溯到窗口内最后一个断点之后，优先在标点/换行处断开
            k = j
            while k > i + 1 and units[k - 1][0] not in _BREAK_CHARS:
                k -= 1
            if k > i + 1:
                j = k
        parts.append("".join(char for char, _ in units[i:j]))
        i = j
    return parts or [""]
