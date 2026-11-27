"""结构化输出校验与哈希测试（真实纯逻辑，无 mock）。"""

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
from app.ai.validation import (  # noqa: E402
    assert_valid,
    canonical_hash,
    content_hash,
    validate_ai_provider_config,
    validate_knowledge_point,
    validate_review_item,
    validate_subject_strategy,
)


def _kp(**overrides):
    data = {
        "subject_id": "11111111-1111-1111-1111-111111111111",
        "title": "虚拟内存",
        "body": "虚拟内存通过页表映射物理页。",
        "summary": "页表映射",
        "difficulty": 3,
        "keywords": ["内存"],
        "tags": ["OS"],
        "status": "draft",
    }
    data.update(overrides)
    return data


def _item(**overrides):
    data = {
        "question_type": "qa",
        "question": "什么是虚拟内存？",
        "answer": "一种内存管理技术",
        "explanation": "",
        "summary": "",
        "options": None,
    }
    data.update(overrides)
    return data


def _strategy(**overrides):
    data = {
        "extraction_prompt": "请抽取 {subject} 的知识点",
        "question_type_preferences": ["qa", "cloze"],
        "glossary": {"IRQL": "中断请求级别"},
        "scheduler_overrides": {"daily_limit": 20},
        "notification_template_overrides": {},
        "prompt_version": "v1",
        "is_active": True,
    }
    data.update(overrides)
    return data


class HashTests(unittest.TestCase):
    def test_canonical_hash_is_64_hex_and_stable(self):
        digest = canonical_hash("Заголовок", "Текст с пробелами")
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, canonical_hash("Заголовок", "Текст с пробелами"))
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_canonical_hash_normalizes_whitespace_only(self):
        self.assertEqual(
            canonical_hash("  Title  ", "a   b\n c"),
            canonical_hash("Title", "a b c"),
        )

    def test_canonical_hash_distinguishes_content(self):
        self.assertNotEqual(canonical_hash("T", "body"), canonical_hash("T", "other"))

    def test_unicode_not_case_folded(self):
        self.assertNotEqual(canonical_hash("Привет", "текст"), canonical_hash("привет", "текст"))

    def test_content_hash_length(self):
        self.assertEqual(len(content_hash("a", "b")), 64)


class KnowledgePointValidationTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_knowledge_point(_kp()), [])

    def test_invalid_difficulty(self):
        for value in (0, 6, "3", True, 3.5):
            with self.subTest(value=value):
                self.assertTrue(validate_knowledge_point(_kp(difficulty=value)))

    def test_invalid_status_and_title(self):
        self.assertTrue(validate_knowledge_point(_kp(status="unknown")))
        self.assertTrue(validate_knowledge_point(_kp(title="")))
        self.assertTrue(validate_knowledge_point(_kp(title="x" * 301)))
        self.assertTrue(validate_knowledge_point(_kp(keywords="not-a-list")))

    def test_missing_fields(self):
        data = _kp()
        del data["body"]
        self.assertTrue(any("缺少契约字段" in e for e in validate_knowledge_point(data)))


class ReviewItemValidationTests(unittest.TestCase):
    def test_valid_all_question_types(self):
        self.assertEqual(validate_review_item(_item()), [])
        self.assertEqual(validate_review_item(_item(question_type="short_explanation")), [])
        self.assertEqual(
            validate_review_item(
                _item(question_type="cloze", question="虚拟内存是 ____ 技术")
            ),
            [],
        )
        self.assertEqual(
            validate_review_item(
                _item(
                    question_type="multiple_choice",
                    question="以下哪项正确？",
                    answer="A",
                    options=["A", "B", "C"],
                )
            ),
            [],
        )

    def test_multiple_choice_requires_options(self):
        for options in (None, [], ["only"], [1, 2]):
            with self.subTest(options=options):
                self.assertTrue(
                    validate_review_item(
                        _item(question_type="multiple_choice", options=options)
                    )
                )

    def test_cloze_requires_placeholder(self):
        errors = validate_review_item(
            _item(question_type="cloze", question="没有空格占位的题面")
        )
        self.assertTrue(any("cloze" in e for e in errors))

    def test_invalid_question_type(self):
        self.assertTrue(validate_review_item(_item(question_type="essay")))

    def test_empty_question_or_answer(self):
        self.assertTrue(validate_review_item(_item(question="")))
        self.assertTrue(validate_review_item(_item(answer="")))


class StrategyAndConfigValidationTests(unittest.TestCase):
    def test_valid_strategy(self):
        self.assertEqual(validate_subject_strategy(_strategy()), [])

    def test_invalid_strategy(self):
        self.assertTrue(
            validate_subject_strategy(_strategy(question_type_preferences=["essay"]))
        )
        self.assertTrue(validate_subject_strategy(_strategy(glossary={"a": 1})))
        self.assertTrue(validate_subject_strategy(_strategy(extraction_prompt="")))
        self.assertTrue(validate_subject_strategy(_strategy(is_active="yes")))

    def test_valid_provider_config(self):
        data = {
            "name": "default", "provider": "deepseek", "model_name": "deepseek-chat",
            "base_url": None, "credential_ref": "AI_API_KEY", "temperature": 0.2,
            "timeout_seconds": 60, "max_retries": 3, "rate_limit_per_minute": None,
            "is_enabled": True, "is_default": True,
        }
        self.assertEqual(validate_ai_provider_config(data), [])
        self.assertTrue(validate_ai_provider_config({**data, "temperature": 3}))
        self.assertTrue(validate_ai_provider_config({**data, "max_retries": -1}))
        self.assertTrue(validate_ai_provider_config({**data, "provider": "x"}))

    def test_assert_valid_raises_structured_error(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            assert_valid(_kp(difficulty=9), validate_knowledge_point, label="kp")
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")
        self.assertTrue(ctx.exception.details)


if __name__ == "__main__":
    unittest.main()
