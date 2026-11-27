"""AI-04 多题型生成、版本化与人工修订保护测试（真实纯逻辑，无 mock）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.ai.config import load_provider_config  # noqa: E402
from app.ai.errors import StructuredOutputError  # noqa: E402
from app.ai.generation import (  # noqa: E402
    ReviewItemDraft,
    apply_generation_policy,
    build_generation_request,
    parse_generation_output,
)
from app.ai.ports import GenerationMeta  # noqa: E402
from app.ai.strategies import default_strategy, strategy_from_mapping  # noqa: E402
from app.ai.validation import (  # noqa: E402
    REVIEW_ITEM_READ_EXTRA_FIELDS,
    REVIEW_ITEM_WRITE_FIELDS,
)

KP_ID = "33333333-3333-3333-3333-333333333333"


def _config():
    return load_provider_config({"AI_PROVIDER": "openai"})


def _strategy(**overrides):
    data = {
        "slug": "s", "name": "学科", "extraction_prompt": "x",
        "question_type_preferences": ["qa", "cloze", "multiple_choice", "short_explanation"],
        "glossary": {}, "scheduler_overrides": {},
        "notification_template_overrides": {}, "prompt_version": "v1", "is_active": True,
    }
    data.update(overrides)
    return strategy_from_mapping(data)


def _items(*items):
    return {"items": list(items)}


def _draft(qtype="qa", **overrides):
    data = {
        "knowledge_point_id": KP_ID,
        "question_type": qtype,
        "question": "问题？",
        "answer": "答案",
        "explanation": "解析",
        "summary": "摘要",
    }
    data.update(overrides)
    return ReviewItemDraft(**data)


class BuildRequestTests(unittest.TestCase):
    def test_request_fields_and_type_intersection(self):
        kp = {"id": KP_ID, "title": "虚拟内存", "body": "页表映射"}
        request = build_generation_request(
            kp, _strategy(), _config(),
            question_types=["cloze", "qa"], count=4, subject_name="Windows 内核",
        )
        self.assertEqual(request.operation, "generate_review_items")
        self.assertEqual(request.prompt_version, "review-item-gen-v1")
        self.assertEqual(request.metadata["question_types"], ["cloze", "qa"])
        self.assertEqual(request.metadata["count"], 4)
        self.assertIn("cloze, qa", request.user)
        self.assertEqual(request.metadata["knowledge_point_id"], KP_ID)

    def test_count_out_of_range_raises(self):
        kp = {"id": KP_ID, "title": "T", "body": "B"}
        for count in (0, 21, -1, "3"):
            with self.subTest(count=count):
                with self.assertRaises(StructuredOutputError):
                    build_generation_request(
                        kp, _strategy(), _config(), count=count
                    )

    def test_no_request_uses_strategy_preference(self):
        kp = {"id": KP_ID, "title": "T", "body": "B"}
        request = build_generation_request(
            kp, _strategy(question_type_preferences=["cloze"]), _config()
        )
        self.assertEqual(request.metadata["question_types"], ["cloze"])


class ParseOutputTests(unittest.TestCase):
    def test_four_question_types(self):
        result = parse_generation_output(
            _items(
                {"question_type": "qa", "question": "什么是X？", "answer": "X是Y"},
                {"question_type": "cloze", "question": "X 是 ____ 技术", "answer": "Y"},
                {"question_type": "multiple_choice", "question": "选哪个？",
                 "answer": "A", "options": ["A", "B"]},
                {"question_type": "short_explanation", "question": "解释X",
                 "answer": "因为Y"},
            ),
            knowledge_point_id=KP_ID,
            meta=GenerationMeta(
                prompt_version="review-item-gen-v1", provider="openai",
                model_name="gpt-4o-mini", provider_config_id="cfg-1",
                ai_call_log_id="log-1",
            ),
        )
        self.assertEqual(len(result.items), 4)
        self.assertEqual(len(result.question_types), 4)
        self.assertTrue(all(item.is_current for item in result.items))
        self.assertTrue(all(item.item_version == 1 for item in result.items))
        mc = next(i for i in result.items if i.question_type == "multiple_choice")
        self.assertEqual(mc.options, ["A", "B"])
        self.assertEqual(mc.ai_call_log_id, "log-1")
        self.assertEqual(mc.model_name, "gpt-4o-mini")
        self.assertEqual(result.prompt_version, "review-item-gen-v1")

    def test_missing_items_raises(self):
        for payload in ({}, {"items": []}, {"items": "x"}):
            with self.subTest(payload=payload):
                with self.assertRaises(StructuredOutputError):
                    parse_generation_output(payload, knowledge_point_id=KP_ID)

    def test_multiple_choice_without_options_rejected(self):
        with self.assertRaises(StructuredOutputError):
            parse_generation_output(
                _items({"question_type": "multiple_choice", "question": "Q",
                        "answer": "A", "options": ["only"]}),
                knowledge_point_id=KP_ID,
            )

    def test_cloze_without_placeholder_rejected(self):
        with self.assertRaises(StructuredOutputError):
            parse_generation_output(
                _items({"question_type": "cloze", "question": "没有占位",
                        "answer": "A"}),
                knowledge_point_id=KP_ID,
            )

    def test_optional_text_defaults_not_fabricated(self):
        result = parse_generation_output(
            _items({"question_type": "qa", "question": "Q", "answer": "A"}),
            knowledge_point_id=KP_ID,
        )
        self.assertEqual(result.items[0].explanation, "")
        self.assertIsNone(result.items[0].options)


class VersionPolicyTests(unittest.TestCase):
    def test_versions_increment_per_question_type(self):
        existing = [_draft("qa", item_version=1, is_current=True)]
        drafts = [_draft("qa"), _draft("qa"), _draft("cloze", question="____ 填空")]
        plan = apply_generation_policy(existing, drafts)
        self.assertEqual([i.item_version for i in plan.to_insert], [2, 3, 1])
        self.assertEqual([i.is_current for i in plan.to_insert], [True, True, True])
        self.assertEqual([i.item_version for i in plan.to_uncurrent], [1])

    def test_manual_revision_is_not_overwritten(self):
        existing = [
            _draft("qa", item_version=1, is_current=True, manual_revision=True,
                   question="人工修订题目")
        ]
        plan = apply_generation_policy(existing, [_draft("qa")])
        self.assertEqual(len(plan.to_insert), 1)
        self.assertEqual(plan.to_insert[0].item_version, 2)
        self.assertFalse(plan.to_insert[0].is_current)  # 人工版仍是 current
        self.assertEqual(plan.to_uncurrent, [])
        self.assertEqual(plan.protected[0].question, "人工修订题目")

    def test_no_existing_items_start_at_version_one(self):
        plan = apply_generation_policy([], [_draft("qa")])
        self.assertEqual(plan.to_insert[0].item_version, 1)
        self.assertTrue(plan.to_insert[0].is_current)

    def test_to_contract_dict_fields(self):
        draft = _draft("qa")
        fields = set(draft.to_contract_dict())
        self.assertEqual(
            fields,
            set(REVIEW_ITEM_WRITE_FIELDS) | set(REVIEW_ITEM_READ_EXTRA_FIELDS),
        )


if __name__ == "__main__":
    unittest.main()
