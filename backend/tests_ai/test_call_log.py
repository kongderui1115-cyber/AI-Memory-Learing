"""AI-01 ``ai_call_logs`` 调用记录结构与状态机测试（真实纯逻辑，无 mock）。"""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.ai.call_log import (  # noqa: E402
    AICallLog,
    CallRecorder,
    validate_call_log_row,
)
from app.ai.errors import ConfigMissingError, InvalidStateError  # noqa: E402
from app.ai.validation import AICALL_LOG_READ_FIELDS  # noqa: E402


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


def _log(**kwargs):
    return AICallLog(
        operation="extract_knowledge",
        provider="deepseek",
        model_name="deepseek-chat",
        prompt_version="kp-extract-v1",
        provider_config_id="cfg-1",
        **kwargs,
    )


@dataclass
class _Result:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class AICallLogTests(unittest.TestCase):
    def test_defaults(self):
        log = _log()
        self.assertEqual(log.status, "pending")
        self.assertEqual(log.attempt_count, 1)
        self.assertIsNone(log.finished_at)
        self.assertIsNotNone(UUID(log.id))
        self.assertIsNotNone(UUID(log.request_id))
        self.assertIn("+00:00", log.started_at)

    def test_start_succeed_records_tokens_and_duration(self):
        clock = Clock(datetime(2026, 1, 1, tzinfo=timezone.utc))
        log = _log(clock=clock)
        log.start()
        self.assertEqual(log.status, "running")
        clock.advance(milliseconds=250)
        log.succeed(input_tokens=11, output_tokens=7)
        self.assertEqual(log.status, "succeeded")
        self.assertEqual(log.total_tokens, 18)
        self.assertEqual(log.duration_ms, 250)
        self.assertIsNotNone(log.finished_at)
        self.assertIsNone(log.error_code)

    def test_explicit_total_tokens_preserved(self):
        log = _log()
        log.start()
        log.succeed(input_tokens=11, output_tokens=7, total_tokens=99)
        self.assertEqual(log.total_tokens, 99)

    def test_fail_records_error_code_and_message(self):
        log = _log()
        log.start()
        log.fail(ConfigMissingError("缺少密钥"))
        self.assertEqual(log.status, "failed")
        self.assertEqual(log.error_code, "CONFIG_MISSING")
        self.assertIn("缺少密钥", log.error_message)
        self.assertIsNotNone(log.finished_at)

    def test_terminal_state_is_immutable(self):
        log = _log()
        log.start()
        log.succeed(input_tokens=1, output_tokens=1)
        for action in (
            log.start,
            lambda: log.fail(ConfigMissingError("x")),
            lambda: log.succeed(input_tokens=1, output_tokens=1),
            log.record_attempt,
        ):
            with self.subTest(action=action):
                with self.assertRaises(InvalidStateError):
                    action()

    def test_cancel_from_pending(self):
        log = _log()
        log.cancel("用户取消")
        self.assertEqual(log.status, "cancelled")
        self.assertIn("用户取消", log.error_message)

    def test_record_attempt_increments(self):
        log = _log()
        log.start()
        log.record_attempt()
        log.record_attempt()
        self.assertEqual(log.attempt_count, 3)

    def test_to_contract_dict_only_contract_fields(self):
        log = _log(metadata={"subject_id": "s1"})
        contract = log.to_contract_dict()
        self.assertEqual(set(contract), set(AICALL_LOG_READ_FIELDS))
        row = log.to_row_dict()
        self.assertIn("metadata", row)
        self.assertEqual(row["metadata"]["subject_id"], "s1")

    def test_validate_call_log_row(self):
        log = _log()
        log.start()
        log.succeed(input_tokens=1, output_tokens=2)
        self.assertEqual(validate_call_log_row(log.to_row_dict()), [])
        bad = log.to_row_dict()
        bad["status"] = "unknown"
        bad["duration_ms"] = -1
        errors = validate_call_log_row(bad)
        self.assertTrue(any("status" in e for e in errors))
        self.assertTrue(any("duration_ms" in e for e in errors))


class CallRecorderTests(unittest.TestCase):
    def test_recorder_lifecycle(self):
        recorder = CallRecorder(
            operation="generate_review_items",
            provider="openai",
            model_name="gpt-4o-mini",
            prompt_version="review-item-gen-v1",
            provider_config_id="cfg-2",
            metadata={"stage": "test"},
        )
        recorder.start()
        recorder.retry()
        recorder.succeed(_Result(input_tokens=5, output_tokens=6, total_tokens=11))
        self.assertEqual(recorder.log.status, "succeeded")
        self.assertEqual(recorder.log.attempt_count, 2)
        self.assertEqual(recorder.log.total_tokens, 11)


if __name__ == "__main__":
    unittest.main()
