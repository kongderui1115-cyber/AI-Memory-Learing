"""AI-03 笔记理解 → 结构化知识点抽取/整理测试（真实纯逻辑，无 mock）。"""

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
from app.ai.extraction import (  # noqa: E402
    KnowledgePointDraft,
    build_extraction_request,
    dedupe_knowledge_points,
    merge_knowledge_points,
    parse_extraction_output,
    reconcile_knowledge_points,
)
from app.ai.ports import GenerationMeta, ProviderResult  # noqa: E402
from app.ai.strategies import default_strategy  # noqa: E402
from app.ai.validation import KNOWLEDGE_POINT_WRITE_FIELDS, canonical_hash  # noqa: E402

SUBJECT_ID = "11111111-1111-1111-1111-111111111111"


def _draft(hash_value: str, **overrides):
    data = {
        "subject_id": SUBJECT_ID,
        "title": "知识点",
        "body": "正文",
        "summary": "摘要",
        "difficulty": 3,
        "keywords": ["a"],
        "tags": ["t"],
        "status": "draft",
        "canonical_hash": hash_value,
    }
    data.update(overrides)
    return KnowledgePointDraft(**data)


def _payload(*points):
    return {"knowledge_points": list(points)}


class BuildRequestTests(unittest.TestCase):
    def test_request_fields(self):
        config = load_provider_config({"AI_PROVIDER": "deepseek", "AI_TEMPERATURE": "0.5"})
        note = {"id": "raw-1", "title": "IRQL", "content_markdown": "DPC at DISPATCH_LEVEL"}
        request = build_extraction_request(
            note, default_strategy(), config, subject_name="Windows 内核"
        )
        self.assertEqual(request.operation, "extract_knowledge")
        self.assertEqual(request.prompt_version, "kp-extract-v1")
        self.assertEqual(request.temperature, 0.5)
        self.assertIn("knowledge_points", str(request.response_schema_hint))
        self.assertIn("DPC at DISPATCH_LEVEL", request.user)
        self.assertEqual(request.metadata["source_raw_note_id"], "raw-1")


class ParseOutputTests(unittest.TestCase):
    def test_valid_two_points(self):
        meta = GenerationMeta(
            prompt_version="kp-extract-v1", provider="deepseek",
            model_name="deepseek-chat", provider_config_id="cfg-1",
            ai_call_log_id="log-1",
        )
        result = parse_extraction_output(
            _payload(
                {"title": "虚拟内存", "body": "页表映射", "summary": "摘要",
                 "difficulty": 2, "keywords": ["内存"], "tags": ["OS"]},
                {"title": "IRQL", "body": "中断级别", "difficulty": 4},
            ),
            subject_id=SUBJECT_ID,
            source_raw_note_id="raw-1",
            meta=meta,
        )
        self.assertEqual(len(result.points), 2)
        first = result.points[0]
        self.assertEqual(first.subject_id, SUBJECT_ID)
        self.assertEqual(first.status, "draft")
        self.assertEqual(first.canonical_hash, canonical_hash("虚拟内存", "页表映射"))
        self.assertEqual(first.source_raw_note_id, "raw-1")
        self.assertEqual(first.prompt_version, "kp-extract-v1")
        self.assertEqual(first.model_name, "deepseek-chat")
        self.assertEqual(result.points[1].summary, "")  # 缺失字段按契约补空，不编造
        self.assertEqual(result.provider, "deepseek")

    def test_accepts_provider_result(self):
        provider_result = ProviderResult(
            content="{}",
            parsed=_payload({"title": "T", "body": "B", "difficulty": 1}),
            input_tokens=1, output_tokens=1, total_tokens=2,
            model_name="m", provider="openai",
        )
        result = parse_extraction_output(
            provider_result, subject_id=SUBJECT_ID, source_raw_note_id="r"
        )
        self.assertEqual(len(result.points), 1)

    def test_missing_or_empty_points_raises(self):
        for payload in ({}, {"knowledge_points": []}, {"knowledge_points": "x"}):
            with self.subTest(payload=payload):
                with self.assertRaises(StructuredOutputError):
                    parse_extraction_output(
                        payload, subject_id=SUBJECT_ID, source_raw_note_id="r"
                    )

    def test_unparsed_provider_result_rejected(self):
        provider_result = ProviderResult(
            content="not json", parsed=None, input_tokens=None,
            output_tokens=None, total_tokens=None, model_name="m", provider="p",
        )
        with self.assertRaises(StructuredOutputError) as ctx:
            parse_extraction_output(
                provider_result, subject_id=SUBJECT_ID, source_raw_note_id="r"
            )
        self.assertIn("伪造", ctx.exception.message)

    def test_invalid_point_raises(self):
        with self.assertRaises(StructuredOutputError):
            parse_extraction_output(
                _payload({"title": "T", "body": "B", "difficulty": 9}),
                subject_id=SUBJECT_ID, source_raw_note_id="r",
            )

    def test_model_cannot_forge_subject_id_or_status(self):
        result = parse_extraction_output(
            _payload({"title": "T", "body": "B", "difficulty": 1,
                      "subject_id": "forged", "status": "active"}),
            subject_id=SUBJECT_ID, source_raw_note_id="r",
        )
        self.assertEqual(result.points[0].subject_id, SUBJECT_ID)
        self.assertEqual(result.points[0].status, "draft")


class DedupeMergeReconcileTests(unittest.TestCase):
    def test_dedupe_by_canonical_hash(self):
        points = [_draft("h1"), _draft("h1"), _draft("h2")]
        self.assertEqual([p.canonical_hash for p in dedupe_knowledge_points(points)],
                         ["h1", "h2"])

    def test_merge_requires_target_uuid(self):
        with self.assertRaises(StructuredOutputError):
            merge_knowledge_points(_draft("h0"), [_draft("h1")])

    def test_merge_sets_merged_terminal_state(self):
        target = _draft("h0", id="22222222-2222-2222-2222-222222222222")
        merged = merge_knowledge_points(target, [_draft("h1"), _draft("h2")])
        self.assertEqual([m.status for m in merged], ["merged", "merged"])
        self.assertTrue(all(m.merged_into_id == target.id for m in merged))
        with self.assertRaises(StructuredOutputError):
            merge_knowledge_points(target, merged)  # 终态只读，不可再次合并

    def test_reconcile_create_update_protect(self):
        existing = [
            _draft("h1", manual_revision=True),
            _draft("h2", status="merged", merged_into_id="x"),
            _draft("h3", keywords=["a"]),
        ]
        incoming = [
            _draft("h1"), _draft("h2"), _draft("h3", keywords=["b"]),
            _draft("h4"), _draft("h4"),  # 同批次重复也应幂等
        ]
        outcome = reconcile_knowledge_points(existing, incoming)
        self.assertEqual([p.canonical_hash for p in outcome.to_create], ["h4"])
        self.assertEqual(len(outcome.to_update), 1)
        self.assertEqual(set(outcome.to_update[0].keywords), {"a", "b"})
        self.assertEqual([p.canonical_hash for p in outcome.protected], ["h1"])
        self.assertEqual([p.canonical_hash for p in outcome.merged], ["h2"])

    def test_manual_revision_content_not_overwritten(self):
        existing = [
            _draft("h1", manual_revision=True, title="人工修订标题", body="人工正文")
        ]
        outcome = reconcile_knowledge_points(existing, [_draft("h1", title="自动标题")])
        self.assertEqual(outcome.to_update, [])
        self.assertEqual(outcome.protected[0].title, "人工修订标题")

    def test_to_contract_dict_only_write_fields(self):
        draft = _draft("h1")
        self.assertEqual(set(draft.to_contract_dict()), set(KNOWLEDGE_POINT_WRITE_FIELDS))
        self.assertIn("canonical_hash", draft.to_row_dict())


if __name__ == "__main__":
    unittest.main()
