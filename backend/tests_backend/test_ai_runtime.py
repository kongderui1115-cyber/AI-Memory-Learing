"""Persistent AI workflow on PostgreSQL with an isolated model HTTP transport."""

import asyncio
import json
import os
import sys
import threading
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import test_core_api as core
import test_notion_runtime as notion_tests
from sqlalchemy import func, select

from app.ai.ports import HttpResponse, StructuredRequest, Transport
from app.ai.errors import ProviderTimeoutError
from app.contracts.workspace import ModelConnect
from app.models import (
    AICallLog,
    AIProviderConfig,
    ChapterJob,
    DailyReviewTask,
    KnowledgePoint,
    KnowledgePointSource,
    ReviewHistory,
    ReviewItem,
    ScheduleState,
    UserSecret,
    WorkspaceProfile,
)
from app.services import ai_runtime, workspace
from app.services.ai_runtime import extract_pending, process_chapter_job
from app.services.common import ServiceError, utcnow


class ModelFixture(Transport):
    def __init__(self):
        self.requests = []
        self.fail_generation = False
        self.card_type = "qa"
        self.title = "知识单元"
        self.answer = None
        self.body = "模型从输入笔记整理出的知识内容"
        self.quote = "原文正文及例子。"
        self.insufficient = False
        self.simulate_error = None

    def post(self, url, headers, body, timeout_seconds):
        request = json.loads(body)
        messages = json.dumps(request["messages"])
        extraction = "knowledge_points" in messages
        self.requests.append("extract" if extraction else "generate")
        if self.simulate_error == "timeout":
            raise ProviderTimeoutError("fixture-only-sensitive-error")
        if self.simulate_error == "invalid_json":
            result = {"choices": [{"message": {"content": "{ malformed JSON"}}]}
            return HttpResponse(status_code=200, body=json.dumps(result).encode())
        if self.fail_generation and not extraction:
            return HttpResponse(status_code=503, body=b'{"error":"fixture-only-private-key"}')
        result = (
            {
                "knowledge_points": [
                    {
                        "title": self.title,
                        "body": self.body,
                        "summary": "摘要",
                        "difficulty": 2,
                        "tags": [],
                        "keywords": [],
                    }
                ]
            }
            if extraction
            else {
                "items": [
                    {
                        "question_type": self.card_type,
                        "question": "概念的定义是 ____。",
                        "answer": self.answer or (
                            self.quote if "原文证据" in request["messages"][-1]["content"] else "依据原文回答"
                        ),
                        "explanation": "结合原文例子理解",
                        "summary": "复习要点",
                    }
                ]
            }
        )
        if extraction and "source_quote" in messages:
            result.update(
                note_summary="原文与示例的摘要",
                information_sufficient=not self.insufficient,
                limitations=["原文没有充分的可学习信息"] if self.insufficient else [],
            )
            if self.insufficient:
                result["knowledge_points"] = []
            else:
                result["knowledge_points"][0].update(
                    source_quote=self.quote,
                    concepts=["示例"],
                    terms=[],
                    relationships=[],
                    prerequisites=[],
                    pitfalls=[],
                    key_points=[],
                    applications=[],
                    review_suggestion="先尝试回忆原文的例子",
                )
        return HttpResponse(
            status_code=200,
            body=json.dumps(
                {
                    "model": "fixture-model",
                    "choices": [
                        {"message": {"content": json.dumps(result)}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                }
            ).encode(),
        )


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class AIAPI(unittest.IsolatedAsyncioTestCase):
    sequence = 140
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request
    subject = core.CoreAPI.subject
    chapter = core.CoreAPI.chapter
    source = notion_tests.NotionAPI.source
    enqueue = notion_tests.NotionAPI.enqueue
    process = notion_tests.NotionAPI.process

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def provider(self, *, name="DeepSeek", default=True):
        reference = "MEMORY_USER_" + self.users[0].id.hex.upper() + "_AI_KEY"
        response = await self.request(
            "POST",
            "/ai/providers",
            key=str(uuid4()),
            body={
                "name": name,
                "provider": "deepseek",
                "model_name": "deepseek-chat",
                "credential_ref": reference,
                "is_default": default,
                "max_retries": 0,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.settings = replace(
            self.settings,
            ai_billing_approved=True,
            raw={**self.settings.raw, reference: "fixture-only-private-key"},
        )
        self.app.state.settings = self.settings
        async with self.owner.transaction() as session:
            profile = await workspace.profile_for(session, self.users[0].id)
            profile.ai_billing_approved = True
        return response.json()

    async def job(self, chapter_id=None):
        if chapter_id is None:
            chapter_id = (await self.chapter(status="completed"))["id"]
        async with self.owner.transaction() as session:
            job = await session.scalar(
                select(ChapterJob)
                .where(ChapterJob.chapter_id == UUID(chapter_id))
                .order_by(ChapterJob.created_at.desc())
                .limit(1)
            )
            return job.id

    async def retry(self, job_id):
        response = await self.request("POST", f"/chapter-jobs/{job_id}/retry", key=str(uuid4()))
        self.assertEqual(response.status_code, 202, response.text)

    async def test_guided_provider_switch_rejects_old_revision_before_transport(self):
        user_id = self.users[0].id
        first = {"provider": "deepseek", "model_name": "deepseek-chat", "api_key": "fixture-a"}
        second = {
            "provider": "openai", "model_name": "fixture-model", "api_key": "fixture-b",
            "billing_approved": True,
        }
        saved = await self.request("PUT", "/workspace/model", body=first)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()["model_key_configured"])
        async with self.owner.transaction() as session:
            provider = await session.scalar(
                select(AIProviderConfig).where(AIProviderConfig.user_id == user_id)
            )
            original = ai_runtime.provider_settings(provider, self.settings)
            old_version = provider.version
        missing_key = await self.request(
            "PUT", "/workspace/model", body={**second, "api_key": None}
        )
        self.assertEqual(missing_key.status_code, 400, missing_key.text)
        saved = await self.request("PUT", "/workspace/model", body=second)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["model"]["provider"], "openai")
        self.assertNotIn("fixture-b", saved.text)
        async with self.owner.transaction() as session:
            provider = await session.get(AIProviderConfig, original.config_id)
            self.assertNotEqual(provider.credential_ref, original.credential_ref)
        transport = ModelFixture()
        with self.assertRaises(ServiceError) as failure:
            await ai_runtime.call_model(
                self.app.state.database, self.settings, user_id, original,
                StructuredRequest("extract", "fixture-v1", "", ""), uuid4(),
                provider_version=old_version, transport=transport,
            )
        self.assertEqual(failure.exception.code, "VERSION_CONFLICT")
        self.assertEqual(transport.requests, [])
        swapped = await self.request(
            "PATCH", f"/ai/providers/{original.config_id}", version=saved.json()["model"]["version"],
            body={"credential_ref": original.credential_ref},
        )
        self.assertEqual(swapped.status_code, 403, swapped.text)
        requests = []

        class BoundModelFixture(ModelFixture):
            def post(self, url, headers, body, timeout_seconds):
                requests.append((url, headers.get("Authorization")))
                return super().post(url, headers, body, timeout_seconds)

        result = await process_chapter_job(
            self.app.state.database, replace(self.settings, ai_billing_approved=True),
            await self.job(), transport=BoundModelFixture(),
        )
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(requests, [("https://api.openai.com/v1/chat/completions", "Bearer fixture-b")] * 2)

    async def test_failed_model_update_rolls_back_key_and_consent(self):
        user_id = self.users[0].id
        original = ModelConnect(provider="deepseek", model_name="deepseek-chat", api_key="fixture-a")
        await workspace.save_model(self.app.state.database, self.settings, user_id, original)
        changed = ModelConnect(
            provider="openai", model_name="fixture-model", api_key="fixture-b", billing_approved=True
        )
        with patch.object(ai_runtime, "set_default_provider", side_effect=RuntimeError("fixture")):
            with self.assertRaises(RuntimeError):
                await workspace.save_model(self.app.state.database, self.settings, user_id, changed)
        async with self.owner.transaction() as session:
            provider = await session.scalar(
                select(AIProviderConfig).where(AIProviderConfig.user_id == user_id)
            )
            refs = (await session.scalars(
                select(UserSecret.name).where(UserSecret.user_id == user_id)
            )).all()
            self.assertEqual(provider.provider, "deepseek")
            self.assertEqual(refs, [provider.credential_ref])
            consent = await session.scalar(select(WorkspaceProfile.ai_billing_approved).where(
                WorkspaceProfile.user_id == user_id
            ))
            self.assertFalse(consent)

    async def test_user_consent_is_required_even_when_deployment_allows_ai(self):
        provider = await self.provider()
        async with self.owner.transaction() as session:
            profile = await workspace.profile_for(session, self.users[0].id)
            profile.ai_billing_approved = False
        response = await self.request("GET", f"/ai/providers/{provider['id']}/readiness")
        self.assertFalse(response.json()["billing_approved"])
        transport = ModelFixture()
        result = await process_chapter_job(
            self.app.state.database, self.settings, await self.job(), transport=transport
        )
        self.assertEqual(result["error_code"], "CONFIG_MISSING", result)
        self.assertEqual(transport.requests, [])

    async def test_model_defaults_scope_and_endpoint_allowlist(self):
        first = await self.provider()
        await self.provider(name="另一个模型")
        response = await self.request("GET", "/ai/providers/" + first["id"])
        self.assertFalse(response.json()["is_default"])
        response = await self.request("GET", "/ai/providers/" + first["id"], user=1)
        self.assertEqual(response.status_code, 404)
        response = await self.request(
            "POST",
            "/ai/providers",
            key=str(uuid4()),
            body={
                "name": "unsafe",
                "provider": "openai_compatible",
                "model_name": "local",
                "base_url": "http://127.0.0.1:5432/",
                "credential_ref": first["credential_ref"],
            },
        )
        self.assertEqual(response.status_code, 403)
        response = await self.request("GET", f"/ai/providers/{first['id']}/readiness")
        self.assertFalse(response.json()["connection_tested"])
        self.assertNotIn("fixture-only-private-key", response.text)

    async def test_no_billing_permission_blocks_call_then_persistent_retry_completes(self):
        await self.provider()
        self.settings = replace(self.settings, ai_billing_approved=False)
        job_id = await self.job()
        transport = ModelFixture()
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["error_code"], "CONFIG_MISSING", result)
        self.assertEqual(transport.requests, [])
        async with self.owner.transaction() as session:
            self.assertIsNone(
                await session.scalar(
                    select(AICallLog.id).where(AICallLog.user_id == self.users[0].id)
                )
            )
        await self.retry(job_id)
        self.settings = replace(self.settings, ai_billing_approved=True)
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["status"], "succeeded", result)
        async with self.owner.transaction() as session:
            point = await session.scalar(
                select(KnowledgePoint).where(KnowledgePoint.user_id == self.users[0].id)
            )
            self.assertEqual(point.status, "active")
            self.assertFalse(point.manual_revision)
            self.assertIsNotNone(
                await session.scalar(
                    select(ScheduleState.id).where(ScheduleState.knowledge_point_id == point.id)
                )
            )
            card = await session.scalar(
                select(ReviewItem).where(ReviewItem.knowledge_point_id == point.id)
            )
            self.assertEqual(card.explanation, "结合原文例子理解")
        await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(transport.requests, ["extract", "generate"])

    async def test_notion_original_is_linked_to_generated_knowledge(self):
        source = await self.source()
        page = notion_tests.notion_page(status="已完成")
        sync = await self.process(await self.enqueue(source), notion_tests.FixtureTransport([page]))
        self.assertEqual(sync["status"], "succeeded", sync)
        await self.provider()
        async with self.owner.transaction() as session:
            job_id = await session.scalar(
                select(ChapterJob.id).where(ChapterJob.user_id == self.users[0].id)
            )
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=ModelFixture()
        )
        self.assertEqual(result["status"], "succeeded", result)
        async with self.owner.transaction() as session:
            link = await session.scalar(
                select(KnowledgePointSource).where(
                    KnowledgePointSource.user_id == self.users[0].id
                )
            )
            job = await session.get(ChapterJob, job_id)
            self.assertEqual(link.source_excerpt, "原文正文及例子。")
            self.assertEqual(str(link.raw_note_id), job.result["source_raw_note_id"])
            point = job.result["analysis"]["knowledge_points"][0]
            self.assertEqual(point["knowledge_point_id"], str(link.knowledge_point_id))
            self.assertEqual(point["source_quote"], link.source_excerpt)
            self.assertEqual(point["source_end"] - point["source_start"], len(link.source_excerpt))
        response = await self.request("GET", "/ai/calls")
        self.assertEqual(len(response.json()["items"]), 2)
        self.assertEqual(response.json()["items"][0]["total_tokens"], 30)
        self.assertNotIn("fixture-only-private-key", response.text)

    async def test_fabricated_quotes_are_rejected_and_bare_notes_can_be_insufficient(self):
        source = await self.source()
        page = notion_tests.notion_page(status="已完成")
        await self.process(await self.enqueue(source), notion_tests.FixtureTransport([page]))
        await self.provider()
        async with self.owner.transaction() as session:
            job_id = await session.scalar(
                select(ChapterJob.id).where(ChapterJob.user_id == self.users[0].id)
            )
        transport = ModelFixture()
        transport.quote = "这句摘录并不存在"
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result, {"status": "failed", "error_code": "VALIDATION_ERROR"})
        await self.retry(job_id)
        transport.insufficient = True
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result, {"status": "succeeded", "count": 0})
        self.assertEqual(transport.requests, ["extract", "extract"])
        async with self.owner.transaction() as session:
            job = await session.get(ChapterJob, job_id)
            self.assertFalse(job.result["analysis"]["information_sufficient"])
            self.assertTrue(job.result["analysis"]["limitations"])
            self.assertFalse(job.result["knowledge_point_ids"])
            self.assertIsNone(
                await session.scalar(
                    select(KnowledgePoint.id).where(KnowledgePoint.user_id == self.users[0].id)
                )
            )

    async def test_generated_notion_answer_requires_exact_source_evidence(self):
        source = await self.source()
        page = notion_tests.notion_page(status="已完成")
        await self.process(await self.enqueue(source), notion_tests.FixtureTransport([page]))
        await self.provider()
        transport = ModelFixture()
        transport.answer = "这个答案从未出现在对应的笔记摘录中"
        async with self.owner.transaction() as session:
            job_id = await session.scalar(select(ChapterJob.id).where(ChapterJob.user_id == self.users[0].id))
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result, {"status": "failed", "error_code": "VALIDATION_ERROR"})
        async with self.owner.transaction() as session:
            self.assertIsNone(await session.scalar(
                select(KnowledgePoint.id).where(KnowledgePoint.user_id == self.users[0].id)
            ))

    async def test_notion_rename_reuses_point_and_retracted_evidence_holds_only_open_tasks(self):
        source = await self.source()
        page = notion_tests.notion_page(status="已完成")
        await self.provider()
        transport = ModelFixture()

        async def analyze(original, text):
            def callback(method, url, payload):
                if url.endswith("/query"):
                    return {"results": [original], "has_more": False}
                return {"results": [notion_tests.paragraph(text)], "has_more": False}

            sync = await self.process(
                await self.enqueue(source), notion_tests.FixtureTransport(callback=callback)
            )
            self.assertEqual(sync["status"], "succeeded")
            async with self.owner.transaction() as session:
                job_id = await session.scalar(
                    select(ChapterJob.id)
                    .where(ChapterJob.user_id == self.users[0].id, ChapterJob.status == "pending")
                )
            result = await process_chapter_job(
                self.app.state.database, self.settings, job_id, transport=transport
            )
            self.assertEqual(result["status"], "succeeded", (original["last_edited_time"], result))
            return job_id

        await analyze(page, transport.quote)
        async with self.owner.transaction() as session:
            point_id = await session.scalar(
                select(KnowledgePoint.id).where(KnowledgePoint.user_id == self.users[0].id)
            )
        timezone = ZoneInfo("Asia/Shanghai")
        now = utcnow()

        async def task_at(moment):
            with patch("app.services.learning.utcnow", return_value=moment):
                response = await self.request(
                    "POST", "/review-batches/generate", key=str(uuid4()),
                    body={
                        "local_date": moment.astimezone(timezone).date().isoformat(),
                        "timezone": timezone.key, "daily_limit": 20,
                    },
                )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(len(response.json()["tasks"]), 1, response.text)
            return UUID(response.json()["tasks"][0]["id"])

        first_id = await task_at(now)
        completion = await self.request(
            "POST", f"/review-tasks/{first_id}/complete", key=str(uuid4()),
            body=core.CoreAPI.completion(),
        )
        self.assertEqual(completion.status_code, 200, completion.text)

        async with self.owner.transaction() as session:
            schedule = await session.scalar(
                select(ScheduleState).where(ScheduleState.knowledge_point_id == point_id)
            )
            next_review = max(now + timedelta(days=1), schedule.due_at + timedelta(minutes=1))
        queued_id = await task_at(next_review)
        started = await self.request("POST", f"/review-tasks/{queued_id}/start", key=str(uuid4()))
        self.assertEqual(started.status_code, 200, started.text)
        original_card = started.json()["review_item_id"]
        original_task_version = started.json()["version"]

        renamed = {**page, "last_edited_time": "2026-11-14T10:00:00Z"}
        transport.title = "重命名后使用同一原文的知识点"
        transport.answer = "原文正文"
        await analyze(renamed, transport.quote + " 补充上下文。")
        content = await self.request("GET", f"/review-tasks/{queued_id}/content")
        self.assertEqual(content.status_code, 200, content.text)
        current = content.json()
        self.assertNotEqual(current["review_item"]["id"], original_card)
        self.assertEqual(current["task"]["review_item_id"], current["review_item"]["id"])
        self.assertEqual(current["task"]["version"], original_task_version + 1)
        self.assertEqual(current["task"]["status"], "in_progress")
        self.assertEqual(current["review_item"]["answer"], transport.answer)
        self.assertEqual(current["knowledge"]["id"], str(point_id))
        self.assertEqual(current["knowledge"]["title"], transport.title)
        self.assertEqual(current["schedule"]["review_count"], 1)

        retracted = {**page, "last_edited_time": "2026-11-14T11:00:00Z"}
        transport.insufficient = True
        job_id = await analyze(retracted, "笔记作者撤回了旧说法。")
        async with self.owner.transaction() as session:
            revised = await session.get(KnowledgePoint, point_id)
            self.assertEqual(revised.status, "draft")
            previous_task = await session.get(DailyReviewTask, first_id)
            queued_task = await session.get(DailyReviewTask, queued_id)
            self.assertEqual(previous_task.status, "completed")
            self.assertEqual(str(previous_task.review_item_id), original_card)
            self.assertEqual((queued_task.status, queued_task.skip_reason), ("cancelled", "source_needs_review"))
            previous_history = await session.scalar(select(ReviewHistory).where(
                ReviewHistory.knowledge_point_id == point_id
            ))
            self.assertEqual(previous_history.task_id, previous_task.id)
            self.assertEqual(previous_history.review_item_id, previous_task.review_item_id)
            job = await session.get(ChapterJob, job_id)
            self.assertEqual(job.result["analysis"]["review_required_point_ids"], [str(point_id)])

    async def test_missing_configuration_stays_blocked_until_a_worker_rechecks(self):
        job_id = await self.job()
        db = self.app.state.database
        transport = ModelFixture()
        result = await process_chapter_job(db, self.settings, job_id, transport=transport)
        self.assertEqual(result, {"status": "blocked", "error_code": "CONFIG_MISSING"})
        self.assertEqual(transport.requests, [])
        async with self.owner.transaction() as session:
            job = await session.get(ChapterJob, job_id)
            self.assertEqual(job.attempt, 0)
            self.assertGreater(job.next_attempt_at, utcnow())
            job.next_attempt_at = utcnow() - timedelta(days=365)
        await self.provider()

        async def process_target(database, settings, pending_id, *, transport):
            if pending_id != job_id:
                return {"status": "deferred"}
            return await process_chapter_job(database, settings, pending_id, transport=transport)

        with patch("app.services.ai_runtime.process_chapter_job", side_effect=process_target):
            result = await extract_pending(db, self.settings, transport=transport)
        self.assertEqual(result["count"], 1)
        self.assertEqual(transport.requests, ["extract", "generate"])

    async def test_invalid_json_and_timeout_do_not_persist_synthetic_knowledge(self):
        await self.provider()
        job_id = await self.job()
        db = self.app.state.database
        transport = ModelFixture()
        for mode in ("invalid_json", "timeout"):
            transport.simulate_error = mode
            result = await process_chapter_job(db, self.settings, job_id, transport=transport)
            self.assertEqual(result["status"], "failed")
            await self.retry(job_id)
        async with self.owner.transaction() as session:
            self.assertIsNone(
                await session.scalar(
                    select(KnowledgePoint.id).where(KnowledgePoint.user_id == self.users[0].id)
                )
            )
            failures = (
                await session.scalars(
                    select(AICallLog).where(AICallLog.user_id == self.users[0].id)
                )
            ).all()
            self.assertEqual(len(failures), 2)
            self.assertEqual({failure.status for failure in failures}, {"failed"})
            self.assertIn("EXTERNAL_TIMEOUT", {failure.error_code for failure in failures})
            self.assertTrue(all("fixture-only" not in failure.error_message for failure in failures))

    async def test_reanalysis_is_owned_idempotent_and_runs_fresh_calls(self):
        await self.provider()
        chapter = await self.chapter(status="completed")
        job_id = await self.job(chapter["id"])
        transport = ModelFixture()
        db = self.app.state.database
        result = await process_chapter_job(db, self.settings, job_id, transport=transport)
        self.assertEqual(result["status"], "succeeded")
        endpoint = f"/chapters/{chapter['id']}/reanalyze"
        key = str(uuid4())
        response = await self.request("POST", endpoint, key=key, user=1)
        self.assertEqual(response.status_code, 404)
        for _ in range(2):
            response = await self.request("POST", endpoint, key=key)
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()["id"], str(job_id))
        self.assertEqual(transport.requests, ["extract", "generate"])
        result = await process_chapter_job(db, self.settings, job_id, transport=transport)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(transport.requests, ["extract", "generate", "extract", "generate"])
        async with self.owner.transaction() as session:
            self.assertEqual(
                await session.scalar(
                    select(func.count(KnowledgePoint.id))
                    .where(KnowledgePoint.user_id == self.users[0].id)
                ),
                1,
            )

    async def test_failed_generation_preserves_call_history_and_reuses_extraction(self):
        await self.provider()
        job_id = await self.job()
        transport = ModelFixture()
        transport.fail_generation = True
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["status"], "failed", result)
        async with self.owner.transaction() as session:
            self.assertIsNone(
                await session.scalar(
                    select(KnowledgePoint.id).where(KnowledgePoint.user_id == self.users[0].id)
                )
            )
        response = await self.request("GET", "/ai/calls")
        self.assertNotIn("fixture-only-private-key", response.text)
        self.assertIn('"status":"failed"', response.text)
        await self.retry(job_id)
        transport.fail_generation = False
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(transport.requests, ["extract", "generate", "generate"])

    async def test_business_failure_rolls_back_and_retry_reuses_both_successful_calls(self):
        await self.provider()
        job_id = await self.job()
        transport = ModelFixture()
        with patch(
            "app.services.ai_runtime.initialize_schedule",
            side_effect=RuntimeError("Injected transaction failure"),
        ):
            result = await process_chapter_job(
                self.app.state.database, self.settings, job_id, transport=transport
            )
        self.assertEqual(result["status"], "failed", result)
        async with self.owner.transaction() as session:
            self.assertIsNone(
                await session.scalar(
                    select(KnowledgePoint.id).where(KnowledgePoint.user_id == self.users[0].id)
                )
            )
            self.assertEqual(
                await session.scalar(
                    select(func.count(AICallLog.id)).where(AICallLog.user_id == self.users[0].id)
                ),
                2,
            )
        await self.retry(job_id)
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(transport.requests, ["extract", "generate"])

    async def test_reopened_chapter_cancels_then_same_revision_resumes(self):
        await self.provider()
        chapter = await self.chapter(status="completed")
        job_id = await self.job(chapter["id"])
        response = await self.request(
            "PATCH",
            "/chapters/" + chapter["id"],
            version=chapter["version"],
            body={"status": "in_progress"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        transport = ModelFixture()
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["status"], "cancelled", result)
        self.assertEqual(transport.requests, [])
        async with self.owner.transaction() as session:
            job = await session.get(ChapterJob, job_id)
            self.assertEqual(job.error_code, "CHAPTER_REOPENED")
        response = await self.request("POST", f"/chapters/{chapter['id']}/complete", key=str(uuid4()))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(await self.job(chapter["id"]), job_id)
        result = await process_chapter_job(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(transport.requests, ["extract", "generate"])

    async def test_concurrent_completion_preserves_current_job(self):
        await self.provider()
        chapter = await self.chapter(status="completed")
        job_id = await self.job(chapter["id"])
        response = await self.request(
            "PATCH", "/chapters/" + chapter["id"], version=chapter["version"],
            body={"status": "in_progress"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        reached, release = asyncio.Event(), asyncio.Event()
        original_lock = ai_runtime.lock_owner

        async def delayed_lock(session, user_id):
            reached.set()
            await asyncio.wait_for(release.wait(), timeout=5)
            return await original_lock(session, user_id)

        transport = ModelFixture()
        db = self.app.state.database
        with patch.object(ai_runtime, "lock_owner", side_effect=delayed_lock):
            attempt = asyncio.create_task(
                process_chapter_job(db, self.settings, job_id, transport=transport)
            )
            try:
                await asyncio.wait_for(reached.wait(), timeout=5)
                response = await self.request(
                    "POST", f"/chapters/{chapter['id']}/complete", key=str(uuid4())
                )
                self.assertEqual(response.status_code, 200, response.text)
            finally:
                release.set()
                outcome = await attempt

        self.assertEqual(outcome, {"status": "deferred"})
        self.assertEqual(transport.requests, [])
        result = await process_chapter_job(db, self.settings, job_id, transport=transport)
        self.assertEqual(result["status"], "succeeded", result)

    async def test_subject_strategy_controls_question_type_and_scheduler(self):
        await self.provider()
        chapter = await self.chapter(status="completed")
        response = await self.request(
            "PUT",
            f"/subjects/{chapter['subject_id']}/strategy",
            body={
                "extraction_prompt": "整理{note_content}",
                "prompt_version": "custom-v1",
                "question_type_preferences": ["cloze"],
                "scheduler_overrides": {"strategy": "fsrs", "target_retention": 0.87},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        transport = ModelFixture()
        transport.card_type = "cloze"
        result = await process_chapter_job(
            self.app.state.database,
            self.settings,
            await self.job(chapter["id"]),
            transport=transport,
        )
        self.assertEqual(result["status"], "succeeded", result)
        async with self.owner.transaction() as session:
            card = await session.scalar(
                select(ReviewItem).where(ReviewItem.user_id == self.users[0].id)
            )
            self.assertEqual(card.question_type, "cloze")
            schedule = await session.scalar(
                select(ScheduleState).where(ScheduleState.user_id == self.users[0].id)
            )
            self.assertEqual(schedule.strategy, "fsrs")
            self.assertAlmostEqual(float(schedule.target_retention), 0.87)

    async def test_manual_knowledge_and_card_remain_protected_on_new_chapter_revision(self):
        await self.provider()
        chapter = await self.chapter(status="completed")
        transport = ModelFixture()
        result = await process_chapter_job(
            self.app.state.database,
            self.settings,
            await self.job(chapter["id"]),
            transport=transport,
        )
        self.assertEqual(result["status"], "succeeded", result)
        response = await self.request("GET", "/knowledge-points")
        point = response.json()["items"][0]
        response = await self.request(
            "PATCH",
            "/knowledge-points/" + point["id"],
            version=point["version"],
            body={"body": "用户人工校订的正文"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.request(
            "POST",
            f"/knowledge-points/{point['id']}/review-items",
            key=str(uuid4()),
            body={"question_type": "qa", "question": "人工题面", "answer": "人工答案"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        response = await self.request(
            "PATCH",
            "/chapters/" + chapter["id"],
            version=chapter["version"],
            body={"content": "修改后的章节笔记"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        transport.body = "新模型输出内容"
        result = await process_chapter_job(
            self.app.state.database,
            self.settings,
            await self.job(chapter["id"]),
            transport=transport,
        )
        self.assertEqual(result["status"], "succeeded", result)
        async with self.owner.transaction() as session:
            point = await session.get(KnowledgePoint, UUID(point["id"]))
            self.assertEqual(point.body, "用户人工校订的正文")
            card = await session.scalar(
                select(ReviewItem).where(
                    ReviewItem.knowledge_point_id == point.id, ReviewItem.is_current
                )
            )
            self.assertEqual(card.question, "人工题面")

    async def test_parallel_extraction_workers_make_one_pair_of_calls(self):
        await self.provider()
        job_id = await self.job()
        entered, release = threading.Event(), threading.Event()
        transport = ModelFixture()
        original_post = transport.post

        def blocking_post(*args):
            if not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Fixture timed out")
            return original_post(*args)

        transport.post = blocking_post
        first = asyncio.create_task(
            process_chapter_job(self.app.state.database, self.settings, job_id, transport=transport)
        )
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
            second = await process_chapter_job(
                self.app.state.database, self.settings, job_id, transport=transport
            )
            self.assertEqual(second["status"], "busy", second)
        finally:
            release.set()
        self.assertEqual((await first)["status"], "succeeded")
        self.assertEqual(transport.requests, ["extract", "generate"])
