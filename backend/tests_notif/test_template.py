"""模板变量渲染 + 按渠道长度自适应裁剪/分段测试（NOTIF-02 / FR-07、FR-08）。"""

import os
import sys
import unittest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.content import (  # noqa: E402
    DEFAULT_BODY_TEMPLATE,
    DEFAULT_TITLE_TEMPLATE,
    build_context,
)
from app.notifications.errors import TemplateRenderError  # noqa: E402
from app.notifications.ports import RenderedMessage  # noqa: E402
from app.notifications.template import (  # noqa: E402
    TemplateRenderer,
    byte_sizer,
    char_sizer,
    split_segments,
    truncate,
)

try:
    from .fakes import make_content  # noqa: E402
except (ImportError, ValueError):
    from fakes import make_content  # noqa: E402


MULTILINGUAL = (
    "【知识点】IRQL 与 DPC\n"
    "IRQL (Interrupt Request Level) 是 Windows 内核的中断请求级别。\n"
    "Что такое DPC? Отложенный вызов процедуры выполняется на DISPATCH_LEVEL.\n"
    "Le DPC ne peut pas accéder à la mémoire paginée, car le paginateur est bloqué.\n"
    "答案要点：DISPATCH_LEVEL 及以上禁止缺页异常，故不能访问分页内存。"
) * 6


class VariableRenderTest(unittest.TestCase):
    def test_default_template_renders_all_variables(self):
        renderer = TemplateRenderer(DEFAULT_TITLE_TEMPLATE, DEFAULT_BODY_TEMPLATE)
        context = build_context(make_content())
        rendered = renderer.render(context)
        self.assertIn("IRQL", rendered.title)
        self.assertIn("【摘要】", rendered.body)
        self.assertIn("【答案要点】", rendered.body)
        self.assertIn("https://example.invalid/review/task-001", rendered.body)
        self.assertNotIn("{title}", rendered.body)
        self.assertNotIn("{", rendered.body)
        self.assertNotIn("}", rendered.body)

    def test_missing_variable_is_strict_error(self):
        renderer = TemplateRenderer("{title}", "{missing_var}")
        with self.assertRaises(TemplateRenderError):
            renderer.render({"title": "X"})

    def test_unknown_placeholder_in_template_rejected(self):
        renderer = TemplateRenderer("{title}", "{title} / {not_in_schema}")
        with self.assertRaises(TemplateRenderError):
            renderer.render({"title": "X"})

    def test_render_is_deterministic(self):
        renderer = TemplateRenderer(DEFAULT_TITLE_TEMPLATE, DEFAULT_BODY_TEMPLATE)
        ctx = build_context(make_content())
        self.assertEqual(renderer.render(ctx), renderer.render(ctx))


class LengthAdaptationTest(unittest.TestCase):
    def test_truncate_char_keeps_within_limit(self):
        text = "汉字测试ABC" * 20
        out = truncate(text, 15, char_sizer)
        self.assertLessEqual(len(out), 15)
        self.assertTrue(out.endswith("…"))

    def test_truncate_byte_never_splits_multibyte_char(self):
        text = "俄文Привет 法语Bonjour 中文你好" * 10
        out = truncate(text, 33, byte_sizer)
        self.assertLessEqual(byte_sizer(out), 33)
        out.encode("utf-8").decode("utf-8")  # 必须仍是合法 UTF-8
        self.assertTrue(out.endswith("…"))

    def test_short_text_unchanged(self):
        self.assertEqual(truncate("短文本", 100, char_sizer), "短文本")
        self.assertEqual(split_segments("短文本", 100, char_sizer), ["短文本"])

    def test_split_segments_roundtrip_with_markers(self):
        segments = split_segments(MULTILINGUAL, 80, char_sizer, add_marker=True)
        self.assertGreater(len(segments), 1)
        for index, segment in enumerate(segments, 1):
            self.assertLessEqual(char_sizer(segment), 80)
            self.assertTrue(segment.startswith(f"({index}/{len(segments)})\n"))
        restored = "".join(seg.split("\n", 1)[1] for seg in segments)
        self.assertEqual(restored, MULTILINGUAL)

    def test_split_segments_byte_mode_is_utf8_safe(self):
        segments = split_segments(MULTILINGUAL, 120, byte_sizer, add_marker=True)
        self.assertGreater(len(segments), 1)
        for segment in segments:
            self.assertLessEqual(byte_sizer(segment), 120)
            segment.encode("utf-8").decode("utf-8")

    def test_split_without_marker_has_no_prefix(self):
        segments = split_segments(MULTILINGUAL, 100, char_sizer, add_marker=False)
        restored = "".join(segments)
        self.assertEqual(restored, MULTILINGUAL)

    def test_adapt_segment_mode_returns_numbered_messages(self):
        renderer = TemplateRenderer(
            "T", "B", max_length=60, length_unit="char", adaptive_mode="segment"
        )
        rendered = renderer.render({})
        messages = renderer.adapt(RenderedMessage(rendered.title, MULTILINGUAL))
        self.assertGreater(len(messages), 1)
        self.assertEqual([m.part_index for m in messages], list(range(1, len(messages) + 1)))
        self.assertTrue(all(m.part_total == len(messages) for m in messages))
        self.assertTrue(all(m.title == rendered.title for m in messages))

    def test_adapt_truncate_mode_single_message(self):
        renderer = TemplateRenderer(
            "T", "B", max_length=40, length_unit="char", adaptive_mode="truncate"
        )
        messages = renderer.adapt(RenderedMessage("标题", MULTILINGUAL))
        self.assertEqual(len(messages), 1)
        self.assertLessEqual(len(messages[0].body), 40)

    def test_adapt_none_mode_returns_original(self):
        renderer = TemplateRenderer("T", "B", max_length=10, adaptive_mode="none")
        original = RenderedMessage("标题", MULTILINGUAL)
        self.assertEqual(renderer.adapt(original), [original])


if __name__ == "__main__":
    unittest.main()
