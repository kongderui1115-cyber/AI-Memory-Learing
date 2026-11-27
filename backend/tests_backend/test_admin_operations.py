"""Real role boundaries and backup archives on the dedicated PostgreSQL test database."""

import asyncio
import os
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_core_api as core

from app.telemetry import Telemetry
from app.config import Settings
from app.services.admin_backup import _postgres_environment
from app.services.common import ServiceError


class TelemetryTests(unittest.TestCase):
    def test_minute_aggregation_window_and_missing_measurements(self):
        clock = [600]
        with (
            patch("app.telemetry._cpu_times", side_effect=[(10, 20), (30, 60), None]),
            patch("app.telemetry._memory", return_value=None),
        ):
            state = Telemetry(clock=lambda: clock[0])
            state.record(200, 10.0)
            state.record(500, 30.0)
            clock[0] += 60
            state.record(404, 20.0)
            summary = state.snapshot(2)
            self.assertEqual((summary["requests"], summary["errors"]), (3, 1))
            self.assertEqual(summary["latency_ms"], 20.0)
            self.assertEqual(summary["p95_latency_ms"], 30.0)
            self.assertEqual(summary["cpu"], 50)
            self.assertIsNone(summary["memory"])
            self.assertEqual(len(summary["buckets"]), 2)
            clock[0] += 120
            self.assertIsNone(state.snapshot(2)["p95_latency_ms"])

    def test_pg_dump_requires_explicit_target_matching_application_dsn(self):
        for url in ("postgresql:///memory_os_test", "postgresql://tester@127.0.0.1/memory_os_test"):
            with self.subTest(url=url), self.assertRaises(ServiceError):
                _postgres_environment(Settings(database_url=url))


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class AdminOperationsTests(unittest.IsolatedAsyncioTestCase):
    sequence = 2021
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def test_operations_require_admin_and_report_real_process_state(self):
        urls = ("/admin/telemetry", "/admin/system/info", "/admin/backups")
        for url in urls:
            anonymous = await self.client.get("/api/v1" + url)
            self.assertEqual(anonymous.status_code, 401)
        for url in urls:
            ordinary = await self.request("GET", url)
            self.assertEqual(ordinary.status_code, 403)

        response = await self.request("GET", "/admin/telemetry?minutes=60", user=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(response.json()["requests"], 0)
        self.assertEqual(response.json()["errors"], 0)
        self.assertEqual(
            (await self.request("GET", "/admin/telemetry?minutes=1441", user=2)).status_code,
            400,
        )
        info = (await self.request("GET", "/admin/system/info", user=2)).json()
        self.assertEqual(info["worker"], "paused")
        self.assertFalse(info["backups_enabled"])
        listed = await self.request("GET", "/admin/backups", user=2)
        self.assertEqual(listed.json(), {"enabled": False, "items": []})
        denied = await self.request("POST", "/admin/backups", key=str(uuid4()), user=2)
        self.assertEqual(denied.status_code, 503, denied.text)

    @unittest.skipUnless(os.environ.get("TEST_PG_DUMP"), "Set TEST_PG_DUMP for real archive smoke")
    async def test_backup_idempotency_and_private_archive_against_test_database(self):
        with TemporaryDirectory() as directory:
            self.app.state.settings = replace(self.settings, raw={
                "ADMIN_BACKUP_DIRECTORY": directory,
                "ADMIN_PG_DUMP_PATH": os.environ["TEST_PG_DUMP"],
            })
            key = str(uuid4())
            denied = await self.request("POST", "/admin/backups", key=key)
            self.assertEqual(denied.status_code, 403)
            created = await self.request("POST", "/admin/backups", key=key, user=2)
            self.assertEqual(created.status_code, 201, created.text)
            item = created.json()
            replay = await self.request("POST", "/admin/backups", key=key, user=2)
            self.assertEqual(replay.json(), item)
            listed = await self.request("GET", "/admin/backups", user=2)
            self.assertEqual(listed.json(), {"enabled": True, "items": [item]})
            files = list(Path(directory).iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes()[:5], b"PGDMP")
            self.assertNotIn(directory, created.text)
