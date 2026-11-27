"""具体知识点内容（FR-07）测试：拒绝空通知、保证具体内容进入正文、Unicode 安全。"""

import os
import sys
import unittest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.content import (  # noqa: E402
    DEFAULT_BODY_TEMPLATE,
    DEFAULT_TITLE_TEMPLATE,
    KnowledgeContent,
    assert_concrete,
    build_context,
    validate_rendered_content,
)
from app.notifications.errors import EmptyContentError  # noqa: E402
from app.notifications.template import TemplateRenderer  # noqa: E402

try:
    from .fakes import make_content  # noqa: E402
except (ImportError, ValueError):
    from fakes import make_content  # noqa: E402


class ConcreteContentTest(unittest.TestCase):
    def test_default_template_contains_title_summary_question_answer_entry(self):
        content = make_content()
        context = build_context(content)
        body = TemplateRenderer(DEFAULT_TITLE_TEMPLATE, DEFAULT_BODY_TEMPLATE).render(context).body
        for fragment in (
            content.title, content.summary, content.question,
            content.answer_points, content.review_url, "【解析】",
        ):
            self.assertIn(fragment, body)
        validate_rendered_content(body, content)

    def test_unicode_multilingual_content_accepted(self):
        content = make_content(
            title="Память и повторение / Mémoire / 记忆",
            summary="Что такое FSRS? Une méthode de révision espacée. 间隔重复算法。",
            question="Comment calculer la rétrogradation ? Как вычислить интервал?",
            answer_points="利用 stability / difficulté / stabilité 计算下一次到期时间。",
            review_url="https://example.invalid/r/abc",
            subject="Русский / Français / 中文",
        )
        assert_concrete(content)
        body = TemplateRenderer(DEFAULT_TITLE_TEMPLATE, DEFAULT_BODY_TEMPLATE).render(
            build_context(content)
        ).body
        validate_rendered_content(body, content)
        self.assertIn("Comment calculer", body)

    def test_empty_title_rejected(self):
        with self.assertRaises(EmptyContentError):
            assert_concrete(make_content(title=""))

    def test_empty_answer_points_rejected(self):
        with self.assertRaises(EmptyContentError):
            assert_concrete(make_content(answer_points=""))

    def test_empty_review_entry_rejected(self):
        with self.assertRaises(EmptyContentError):
            assert_concrete(make_content(review_url=""))

    def test_empty_summary_and_question_rejected(self):
        with self.assertRaises(EmptyContentError):
            assert_concrete(make_content(summary="", question=""))

    def test_empty_notice_slogan_rejected(self):
        with self.assertRaises(EmptyContentError):
            assert_concrete(make_content(
                title="您有 5 条待复习", summary="", question="", answer_points="",
                review_url="https://example.invalid/r",
            ))

    def test_tiny_placeholder_blocks_rejected(self):
        with self.assertRaises(EmptyContentError):
            assert_concrete(make_content(summary="略", question="?", answer_points="A"))

    def test_rendered_body_missing_answer_points_rejected(self):
        content = make_content()
        # 模板被改坏：正文只剩标题，不含答案要点/摘要/问题/入口
        body = TemplateRenderer("{title}", "{title}").render(build_context(content)).body
        with self.assertRaises(EmptyContentError):
            validate_rendered_content(body, content)

    def test_rendered_body_missing_review_entry_rejected(self):
        content = make_content()
        template = "{title}\n{summary}\n{question}\n{answer_points}"  # 故意漏掉复习入口
        body = TemplateRenderer("{title}", template).render(build_context(content)).body
        with self.assertRaises(EmptyContentError):
            validate_rendered_content(body, content)

    def test_empty_notice_text_in_rendered_body_rejected(self):
        content = make_content()
        with self.assertRaises(EmptyContentError):
            validate_rendered_content("您有 5 条待复习，请及时处理", content)


if __name__ == "__main__":
    unittest.main()
