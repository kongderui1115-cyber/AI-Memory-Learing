"""契约零偏差测试（真实逻辑，无 mock）。

用标准库 ``ast`` 解析 Chief Architect 独占、共享只读的冻结契约文件
``backend/app/contracts/enums.py`` / ``models.py``，逐项比对本模块复刻的
枚举值与字段名；并核对错误码与数据库列名确实存在于治理文档中。
不 import pydantic，因此可在未安装依赖的环境中真实运行。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _support  # noqa: E402  真实契约 ast 工具（非 mock）
from app.ai import validation  # noqa: E402


class EnumAlignmentTests(unittest.TestCase):
    def test_enum_values_match_frozen_contract(self):
        actual = _support.contract_enum_values()
        pairs = [
            ("AIProviderType", validation.AI_PROVIDER_TYPES),
            ("AICallStatus", validation.AI_CALL_STATUSES),
            ("QuestionType", validation.QUESTION_TYPES),
            ("KnowledgePointStatus", validation.KNOWLEDGE_POINT_STATUSES),
            ("RunStatus", validation.RUN_STATUSES),
        ]
        for class_name, mine in pairs:
            with self.subTest(enum=class_name):
                self.assertIn(class_name, actual)
                self.assertEqual(set(mine), actual[class_name])

    def test_literal_enums_documented(self):
        api = _support.read_api_contract()
        schema = _support.read_database_schema()
        for value in (*validation.TRIGGER_TYPES, *validation.SOURCE_TYPES):
            with self.subTest(value=value):
                self.assertIn(f"'{value}'", schema)
        self.assertEqual(validation.TRIGGER_TYPES, {"manual", "scheduled"})
        self.assertEqual(validation.SOURCE_TYPES, {"database", "page_tree"})
        self.assertIn("SyncRunRead", api)


class ModelFieldAlignmentTests(unittest.TestCase):
    def test_model_fields_match_frozen_contract(self):
        pairs = [
            ("AICallLogRead", validation.AICALL_LOG_READ_FIELDS),
            ("KnowledgePointWrite", validation.KNOWLEDGE_POINT_WRITE_FIELDS),
            ("ReviewItemWrite", validation.REVIEW_ITEM_WRITE_FIELDS),
            ("ReviewItemRead", validation.REVIEW_ITEM_READ_EXTRA_FIELDS),
            ("SubjectStrategyWrite", validation.SUBJECT_STRATEGY_WRITE_FIELDS),
            ("AIProviderConfigWrite", validation.AI_PROVIDER_CONFIG_WRITE_FIELDS),
            ("SyncRunRead", validation.SYNC_RUN_READ_FIELDS),
            ("RawNoteRead", validation.RAW_NOTE_READ_FIELDS),
        ]
        for class_name, mine in pairs:
            with self.subTest(model=class_name):
                self.assertEqual(set(mine), _support.contract_model_fields(class_name))


class DocumentationAlignmentTests(unittest.TestCase):
    def test_error_codes_exist_in_api_contract(self):
        api = _support.read_api_contract()
        for code in (
            "CONFIG_MISSING", "EXTERNAL_SERVICE_ERROR", "EXTERNAL_TIMEOUT",
            "RATE_LIMITED", "INVALID_STATE", "VALIDATION_ERROR",
            "SEMANTIC_VALIDATION_ERROR",
        ):
            with self.subTest(code=code):
                self.assertIn(f"`{code}`", api)

    def test_database_columns_exist_in_schema(self):
        schema = _support.read_database_schema()
        for column in (
            "ai_call_logs", "prompt_version", "total_tokens", "duration_ms",
            "raw_notes", "content_hash", "external_version", "last_edited_watermark",
            "sync_runs", "idempotency_key", "canonical_hash", "manual_revision",
            "subject_strategies", "review_items", "item_version",
        ):
            with self.subTest(column=column):
                self.assertIn(column, schema)

    def test_idempotency_unique_constraint_documented(self):
        schema = _support.read_database_schema()
        self.assertIn(
            "UQ `(data_source_id,external_page_id,external_version)`", schema
        )
        self.assertIn("UQ `(user_id,idempotency_key)`", schema)


if __name__ == "__main__":
    unittest.main()
