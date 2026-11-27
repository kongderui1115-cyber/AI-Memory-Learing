"""提示词版本与模板渲染测试（真实纯逻辑，无 mock，含多语言 Unicode）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.ai.errors import StructuredOutputError  # noqa: E402
from app.ai.prompts import (  # noqa: E402
    PROMPT_VERSION_EVALUATION,
    PROMPT_VERSION_EXTRACTION,
    PROMPT_VERSION_GENERATION,
    build_extraction_prompt,
    build_generation_prompt,
    render_template,
)
from app.ai.strategies import default_strategy, strategy_from_mapping  # noqa: E402


class RenderTemplateTests(unittest.TestCase):
    def test_basic_replacement(self):
        self.assertEqual(
            render_template("Hello {name}, today is {day}", {"name": "Ana", "day": "Mon"}),
            "Hello Ana, today is Mon",
        )

    def test_escaped_braces_are_literal(self):
        result = render_template("JSON 形如 {{ \"a\": {value} }}", {"value": "1"})
        self.assertEqual(result, 'JSON 形如 { "a": 1 }')

    def test_strict_unknown_variable_raises(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            render_template("{known} {unknown}", {"known": "x"})
        self.assertIn("unknown", ctx.exception.message)
        self.assertTrue(any(d.field == "unknown" for d in ctx.exception.details))

    def test_nonstrict_keeps_unknown_placeholder(self):
        self.assertEqual(
            render_template("{a} {b}", {"a": "1"}, strict=False), "1 {b}"
        )

    def test_non_string_template_rejected(self):
        with self.assertRaises(StructuredOutputError):
            render_template(123, {})  # type: ignore[arg-type]

    def test_unicode_values_preserved(self):
        self.assertEqual(
            render_template("Term: {term}", {"term": "падеж / subjonctif / 内核"}),
            "Term: падеж / subjonctif / 内核",
        )


class BuildPromptTests(unittest.TestCase):
    def test_default_extraction_prompt_contains_schema_and_note(self):
        system, user = build_extraction_prompt(
            default_strategy(),
            subject_name="Windows 内核",
            note_title="IRQL 笔记",
            note_content="DPC 运行在 DISPATCH_LEVEL",
        )
        self.assertIn("JSON", system)
        self.assertIn("Windows 内核", user)
        self.assertIn("DPC 运行在 DISPATCH_LEVEL", user)
        self.assertIn("knowledge_points", user)  # schema 变量真实注入
        self.assertNotIn("{subject}", user)
        self.assertNotIn("{schema}", user)

    def test_custom_subject_prompt_overrides_default(self):
        strategy = strategy_from_mapping(
            {
                "slug": "russian",
                "name": "俄语",
                "extraction_prompt": "学科={subject}; 术语={glossary}; 原文={note_content}",
                "question_type_preferences": ["cloze"],
                "glossary": {"вид": "动词体", "падеж": "格"},
                "scheduler_overrides": {},
                "notification_template_overrides": {},
                "prompt_version": "ru-v1",
                "is_active": True,
            }
        )
        _, user = build_extraction_prompt(
            strategy,
            subject_name="俄语",
            note_title="Виды глагола",
            note_content="Совершенный и несовершенный вид",
            prompt_version="ru-v1",
        )
        self.assertIn("学科=俄语", user)
        self.assertIn("вид: 动词体", user)
        self.assertIn("Совершенный и несовершенный вид", user)
        self.assertEqual(strategy.prompt_version, "ru-v1")
        self.assertIn("knowledge_points", user)

    def test_generation_prompt_contains_types_and_count(self):
        _, user = build_generation_prompt(
            default_strategy(),
            subject_name="法语",
            knowledge_title="Subjonctif",
            knowledge_body="Le subjonctif s'emploie après...",
            question_types=["cloze", "multiple_choice"],
            count=5,
        )
        self.assertIn("cloze, multiple_choice", user)
        self.assertIn("5", user)
        self.assertIn("Subjonctif", user)
        self.assertIn("multiple_choice", user)  # schema 中的题型枚举
        self.assertNotIn("{count}", user)

    def test_generation_custom_system_prompt(self):
        strategy = strategy_from_mapping(
            {
                "slug": "math", "name": "数学",
                "extraction_prompt": "x",
                "question_type_preferences": ["qa"], "glossary": {},
                "scheduler_overrides": {}, "notification_template_overrides": {},
                "prompt_version": "m1", "is_active": True,
                "system_prompt": "只输出严谨的数学 JSON",
            }
        )
        system, _ = build_generation_prompt(
            strategy,
            subject_name="数学",
            knowledge_title="导数",
            knowledge_body="f'(x)",
            question_types=["qa"],
            count=1,
        )
        self.assertEqual(system, "只输出严谨的数学 JSON")

    def test_prompt_versions_are_distinct(self):
        self.assertEqual(
            len({PROMPT_VERSION_EXTRACTION, PROMPT_VERSION_GENERATION, PROMPT_VERSION_EVALUATION}),
            3,
        )


if __name__ == "__main__":
    unittest.main()
