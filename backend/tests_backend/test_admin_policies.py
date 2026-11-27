"""Isolated role, version, redaction and scheduling checks for admin policies."""

import asyncio
import os
import sys
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import func, select

import test_core_api as core

from app.config import Settings
from app.contracts.admin_policies import MemorySimulationRequest
from app.models import AICallLog, AuditEvent, ScheduleState
from app.services.admin_policies import SIMULATION_START, simulate_memory


class MemoryPolicySimulation(unittest.TestCase):
    def test_simulation_uses_fixed_and_adaptive_schedulers(self):
        fixed = MemorySimulationRequest(strategy="ebbinghaus", intervals_days=[2, 5], ratings=["good", "again"])
        result = simulate_memory(Settings(), fixed)
        self.assertTrue(result["simulation"])
        self.assertEqual(result["steps"][0]["reviewed_at"], SIMULATION_START + timedelta(days=2))
        self.assertEqual(result["steps"][0]["interval_days"], 5)
        self.assertEqual(result["steps"][1]["interval_days"], 2)
        self.assertIsNone(result["steps"][0]["retrievability"])
        fsrs = MemorySimulationRequest(strategy="fsrs", target_retention=0.92, ratings=["good", "hard"])
        adaptive = simulate_memory(Settings(), fsrs)
        self.assertEqual(adaptive, simulate_memory(Settings(), fsrs))
        self.assertEqual(adaptive["steps"][0]["reviewed_at"], SIMULATION_START)
        self.assertIsNotNone(adaptive["steps"][0]["stability"])
        self.assertIsNotNone(adaptive["steps"][1]["retrievability"])


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class AdminPoliciesAPI(unittest.IsolatedAsyncioTestCase):
    sequence = 217
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request
    subject = core.CoreAPI.subject

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def test_model_management_is_role_version_and_owner_scoped(self):
        response = await self.client.get("/api/v1/admin/model-providers")
        self.assertEqual(response.status_code, 401)
        response = await self.request("GET", "/admin/model-providers")
        self.assertEqual(response.status_code, 403)
        model_body = {
            "provider": "deepseek", "model_name": "deepseek-chat", "api_key": "fixture-not-an-api-key",
            "billing_approved": True,
        }
        for user in (0, 1):
            response = await self.request("PUT", "/workspace/model", body=model_body, user=user)
            self.assertEqual(response.status_code, 200, response.text)
        provider_ref = f"MEMORY_USER_{self.users[0].id.hex.upper()}_ENV_MODEL"
        secondary = await self.request("POST", "/ai/providers", body={
            "name": "备用模型", "provider": "deepseek", "model_name": "deepseek-chat",
            "credential_ref": provider_ref, "is_enabled": True, "is_default": False,
        }, key=str(uuid4()))
        self.assertEqual(secondary.status_code, 201, secondary.text)
        secondary_id = secondary.json()["id"]
        path = f"/admin/model-providers?user_id={self.users[0].id}"
        response = await self.request("GET", path, user=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("credential_ref", response.text)
        self.assertNotIn(provider_ref, response.text)
        original = next(row for row in response.json()["items"] if row["is_default"])
        self.assertEqual(len(response.json()["items"]), 2)
        self.assertEqual(original["configuration_status"], "billing_paused")
        with patch("app.services.ai_runtime.AIExecutionService.complete", side_effect=AssertionError("outbound")):
            ready = await self.request("GET", f"/admin/model-providers/{original['id']}/readiness", user=2)
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertTrue(ready.json()["key_configured"])
        self.assertTrue(ready.json()["user_billing_approved"])
        self.assertFalse(ready.json()["global_billing_approved"])
        self.assertFalse(ready.json()["connection_tested"])
        self.assertNotIn(model_body["api_key"], ready.text)

        model_path = f"/admin/model-providers/{secondary_id}"
        version = secondary.json()["version"]
        response = await self.request("PATCH", model_path, body={"is_default": True}, version=version)
        self.assertEqual(response.status_code, 403)
        response = await self.request("PATCH", model_path, user=2, body={
            "is_default": True, "base_url": "https://outside.example.test",
        }, version=version)
        self.assertEqual(response.status_code, 400, response.text)
        response = await self.request("PATCH", model_path, user=2, body={"is_default": True}, version=version)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["is_default"])
        response = await self.request("PATCH", model_path, user=2, body={"is_enabled": False}, version=version)
        self.assertEqual(response.status_code, 409)
        response = await self.request("PATCH", model_path, user=2, body={"is_enabled": False}, version=version + 1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["is_default"])
        self.assertFalse(response.json()["is_enabled"])
        untouched = await self.request("GET", f"/admin/model-providers?user_id={self.users[1].id}", user=2)
        self.assertTrue(untouched.json()["items"][0]["is_default"])
        async with self.owner.transaction() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(AICallLog).where(
                AICallLog.user_id == self.users[0].id
            )), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.actor_id == self.users[2].id,
                AuditEvent.target_user_id == self.users[0].id,
                AuditEvent.action == "admin_model_policy_updated",
            )), 2)

    async def test_subject_policy_changes_future_schedules_and_simulation_is_read_only(self):
        subject = await self.subject()
        created = await self.request("PUT", f"/subjects/{subject['id']}/strategy", body={
            "extraction_prompt": "仅使用原始笔记",
            "prompt_version": "admin-policy-test-v1",
            "scheduler_overrides": {"strategy": "ebbinghaus", "intervals_days": [2, 5]},
        })
        self.assertEqual(created.status_code, 200, created.text)
        before = await self.create_point(subject, "原调度")
        response = await self.request("GET", f"/admin/memory/policies?user_id={self.users[0].id}", user=2)
        self.assertEqual(response.status_code, 200, response.text)
        policy = response.json()["items"][0]
        self.assertEqual(policy["intervals_days"], [2, 5])
        path = f"/admin/memory/policies/{policy['id']}"
        edit = {"strategy": "fsrs", "target_retention": 0.89}
        self.assertEqual((await self.request("PATCH", path, body=edit, version=policy["version"])).status_code, 403)
        response = await self.request("PATCH", path, body=edit, user=2, version=policy["version"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["strategy"], "fsrs")
        self.assertEqual(response.json()["target_retention"], 0.89)
        self.assertEqual((await self.request("PATCH", path, body=edit, user=2, version=policy["version"])).status_code, 409)
        after = await self.create_point(subject, "新调度")
        for point, strategy in ((before, "ebbinghaus"), (after, "fsrs")):
            response = await self.request("GET", f"/knowledge-points/{point['id']}/schedule")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["strategy"], strategy)
        request = {"strategy": "fsrs", "ratings": ["good", "again"]}
        path = "/admin/memory/simulations"
        self.assertEqual((await self.request("POST", path, body=request)).status_code, 403)
        response = await self.request("POST", path, body=request, user=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["simulation"])
        self.assertEqual(len(response.json()["steps"]), 2)
        async with self.owner.transaction() as session:
            count = await session.scalar(select(func.count()).select_from(ScheduleState).where(
                ScheduleState.user_id == self.users[0].id
            ))
        self.assertEqual(count, 2)

    async def create_point(self, subject, title):
        response = await self.request("POST", "/knowledge-points", key=str(uuid4()), body={
            "subject_id": subject["id"], "title": title, "body": "原始资料", "summary": "摘要",
            "difficulty": 2, "status": "active",
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()
