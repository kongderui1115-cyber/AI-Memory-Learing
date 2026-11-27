"""Runtime checks using real FastAPI and PostgreSQL DDL compilation."""
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from app.main import create_app
from app.api.health import REQUIRED_SCHEMA_REVISION
from app.config import Settings, load_settings
from app.models import target_metadata
from app.worker import execute


class RuntimeTests(unittest.TestCase):
    def test_liveness_and_missing_configuration(self):
        with TestClient(create_app(load_env=False)) as client:
            response = client.get('/api/v1/health/live')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'status': 'ok'})
            response = client.get('/api/v1/health/ready')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['checks']['config']['code'], 'CONFIG_MISSING')

    def test_all_models_compile_as_postgresql(self):
        self.assertGreaterEqual(len(target_metadata.tables), 20)
        for table in target_metadata.sorted_tables:
            with self.subTest(table=table.name):
                sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
                self.assertIn('CREATE TABLE', sql)

    def test_readiness_rejects_old_or_unexpected_database_schema(self):
        settings = Settings(database_url="postgresql://test@127.0.0.1/local_test")
        for revisions, expected in [
            ([], 503),
            (["0005_guided_setup"], 503),
            ([REQUIRED_SCHEMA_REVISION, "other_revision"], 503),
            ([REQUIRED_SCHEMA_REVISION], 200),
        ]:
            @asynccontextmanager
            async def transaction():
                yield SimpleNamespace(
                    execute=AsyncMock(),
                    scalars=AsyncMock(return_value=revisions),
                )

            database = SimpleNamespace(transaction=transaction, close=AsyncMock())
            with self.subTest(revisions=revisions), patch("app.main.Database", return_value=database):
                with TestClient(create_app(settings)) as client:
                    result = client.get("/health/ready")
                self.assertEqual(result.status_code, expected)
                if expected == 503:
                    self.assertEqual(result.json()["checks"]["database"]["code"], "SCHEMA_VERSION_MISMATCH")


class WorkerPauseTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_cli_route_is_paused_without_accessing_database(self):
        with patch("app.worker.load_settings", return_value=Settings()), patch("app.worker.Database") as db:
            for job in ("sync-notion", "extract-chapters", "generate-daily-tasks", "send-daily-digest"):
                self.assertEqual(await execute(job), {"status": "paused", "job": job})
        db.assert_not_called()

    def test_unset_background_defaults_to_paused(self):
        settings = load_settings({
            "DATABASE_URL": "postgresql://test@127.0.0.1/local_test",
            "SECRET_KEY": "test-key-with-at-least-thirty-two-characters",
        })
        self.assertFalse(settings.background_tasks_enabled)

if __name__ == '__main__':
    unittest.main()
