"""AI-06 数据驱动学科策略测试（真实纯逻辑，无 mock，含新增学科与 Unicode）。"""

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
from app.ai.strategies import (  # noqa: E402
    StrategyRegistry,
    built_in_presets,
    default_strategy,
    load_registry_from_config,
    render_notification_override,
    resolve_notification_overrides,
    resolve_question_types,
    resolve_scheduler_overrides,
    strategy_from_mapping,
)
from app.ai.validation import SUBJECT_STRATEGY_WRITE_FIELDS  # noqa: E402


def _config(slug="test", name="测试", **overrides):
    data = {
        "slug": slug,
        "name": name,
        "extraction_prompt": "抽取 {subject} 的知识点: {note_content}",
        "question_type_preferences": ["qa", "cloze"],
        "glossary": {"term": "释义"},
        "scheduler_overrides": {"daily_limit": 10},
        "notification_template_overrides": {"review_digest": "【{subject}】{title}"},
        "prompt_version": "v1",
        "is_active": True,
    }
    data.update(overrides)
    return data


class StrategyParsingTests(unittest.TestCase):
    def test_valid_mapping(self):
        strategy = strategy_from_mapping(_config())
        self.assertEqual(strategy.slug, "test")
        self.assertEqual(strategy.question_type_preferences, ("qa", "cloze"))
        self.assertEqual(strategy.glossary["term"], "释义")
        self.assertTrue(strategy.is_active)

    def test_unknown_field_rejected(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            strategy_from_mapping(_config(typo_field=1))
        self.assertIn("typo_field", ctx.exception.message)

    def test_invalid_question_type_rejected(self):
        with self.assertRaises(StructuredOutputError):
            strategy_from_mapping(_config(question_type_preferences=["essay"]))

    def test_missing_contract_field_rejected(self):
        data = _config()
        del data["extraction_prompt"]
        with self.assertRaises(StructuredOutputError):
            strategy_from_mapping(data)

    def test_to_contract_dict_only_seven_fields(self):
        strategy = strategy_from_mapping(_config(subject_id="uuid-1", language_code="ru"))
        contract = strategy.to_contract_dict()
        self.assertEqual(set(contract), set(SUBJECT_STRATEGY_WRITE_FIELDS))
        self.assertEqual(contract["question_type_preferences"], ["qa", "cloze"])

    def test_round_trip_config_mapping(self):
        original = _config(subject_id="u1", language_code="fr", system_prompt="sys")
        restored = strategy_from_mapping(
            strategy_from_mapping(original).to_config_mapping()
        )
        self.assertEqual(restored.slug, "test")
        self.assertEqual(restored.subject_id, "u1")
        self.assertEqual(restored.language_code, "fr")


class RegistryTests(unittest.TestCase):
    def test_default_fallback_for_unknown_subject(self):
        registry = StrategyRegistry()
        resolved = registry.resolve(slug="does-not-exist")
        self.assertEqual(resolved.slug, "__default__")
        self.assertEqual(len(resolved.question_type_preferences), 4)

    def test_new_subject_needs_no_code_change(self):
        """新增一个任意学科：仅注册一条配置即可贯穿解析/题型/模板覆盖。"""
        registry = load_registry_from_config(include_builtin=False)
        new_subject = _config(
            slug="geologie", name="地质学",
            question_type_preferences=["multiple_choice", "short_explanation"],
            glossary={"стратиграфия": "地层学", "faille": "断层"},
            scheduler_overrides={"fsrs_target_retention": 0.88},
            notification_template_overrides={"review_digest": "[{subject}] {title}"},
        )
        registry.register(strategy_from_mapping(new_subject))
        resolved = registry.resolve(slug="geologie")
        self.assertEqual(resolved.name, "地质学")
        self.assertIn("faille", resolved.glossary)
        self.assertEqual(
            resolve_question_types(resolved), ["multiple_choice", "short_explanation"]
        )
        self.assertEqual(
            render_notification_override(
                resolved, "review_digest", {"subject": "地质学", "title": "断层"}
            ),
            "[地质学] 断层",
        )

    def test_builtin_presets_all_valid(self):
        presets = built_in_presets()
        self.assertEqual(len(presets), 6)
        for slug, config in presets.items():
            with self.subTest(slug=slug):
                strategy = strategy_from_mapping(config)
                self.assertEqual(strategy.slug, slug)
                self.assertTrue(strategy.question_type_preferences)

    def test_registry_builtin_plus_new(self):
        registry = load_registry_from_config([_config(slug="chemistry", name="化学")])
        self.assertEqual(len(registry.slugs), 7)
        self.assertEqual(registry.resolve(slug="chemistry").name, "化学")

    def test_resolve_by_subject_id(self):
        registry = StrategyRegistry()
        registry.register(
            strategy_from_mapping(_config(slug="s", subject_id="id-42"))
        )
        self.assertEqual(registry.resolve(subject_id="id-42").slug, "s")

    def test_empty_slug_rejected(self):
        with self.assertRaises(StructuredOutputError):
            StrategyRegistry().register(strategy_from_mapping(_config(slug="", name="")))


class QuestionTypeResolutionTests(unittest.TestCase):
    def test_no_request_uses_preference(self):
        strategy = strategy_from_mapping(_config())
        self.assertEqual(resolve_question_types(strategy), ["qa", "cloze"])
        self.assertEqual(resolve_question_types(strategy, []), ["qa", "cloze"])

    def test_default_strategy_uses_all_four(self):
        self.assertEqual(len(resolve_question_types(default_strategy())), 4)

    def test_intersection_preserves_request_order(self):
        strategy = strategy_from_mapping(_config())
        self.assertEqual(
            resolve_question_types(strategy, ["cloze", "qa", "multiple_choice"]),
            ["cloze", "qa"],
        )

    def test_invalid_type_raises(self):
        with self.assertRaises(StructuredOutputError):
            resolve_question_types(default_strategy(), ["essay"])

    def test_empty_intersection_raises_not_silently_downgraded(self):
        strategy = strategy_from_mapping(_config(question_type_preferences=["qa"]))
        with self.assertRaises(StructuredOutputError) as ctx:
            resolve_question_types(strategy, ["cloze"])
        self.assertIn("无交集", ctx.exception.message)


class OverrideTests(unittest.TestCase):
    def test_scheduler_overrides_win(self):
        strategy = strategy_from_mapping(_config(scheduler_overrides={"daily_limit": 10}))
        merged = resolve_scheduler_overrides(
            strategy, {"daily_limit": 30, "timezone": "UTC"}
        )
        self.assertEqual(merged["daily_limit"], 10)
        self.assertEqual(merged["timezone"], "UTC")

    def test_notification_overrides_win_and_do_not_mutate(self):
        strategy = strategy_from_mapping(
            _config(notification_template_overrides={"max_length": 200})
        )
        base = {"max_length": 1000}
        merged = resolve_notification_overrides(strategy, base)
        self.assertEqual(merged["max_length"], 200)
        self.assertEqual(base["max_length"], 1000)

    def test_render_notification_override_unicode(self):
        strategy = strategy_from_mapping(
            _config(
                notification_template_overrides={
                    "review_digest": "【{subject}】{title}\n{summary}"
                }
            )
        )
        rendered = render_notification_override(
            strategy,
            "review_digest",
            {"subject": "Русский", "title": "Падежи", "summary": "六格"},
        )
        self.assertIn("Русский", rendered)
        self.assertIn("六格", rendered)

    def test_render_override_falls_back_to_default(self):
        self.assertEqual(
            render_notification_override(
                default_strategy(), "missing", {}, default="fallback {title}"
            ),
            "fallback {title}",
        )


if __name__ == "__main__":
    unittest.main()
