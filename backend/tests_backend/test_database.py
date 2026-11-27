"""Session lifecycle tests. No network connection or SQL is performed."""
import unittest
from app.config import Settings
from app.database import Database


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_transaction_lifecycle_without_connection(self):
        database = Database(Settings(database_url='postgresql://local:local@127.0.0.1:65432/isolated'))
        try:
            async with database.transaction() as session:
                self.assertTrue(session.in_transaction())
            self.assertFalse(session.in_transaction())
            with self.assertRaisesRegex(ValueError, 'abort'):
                async with database.transaction() as failed_session:
                    raise ValueError('abort')
            self.assertFalse(failed_session.in_transaction())
            self.assertEqual(database.engine.url.drivername, 'postgresql+psycopg')
        finally:
            await database.close()