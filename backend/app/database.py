"""PostgreSQL sessions with explicit transaction boundaries."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, assert_database_configured


class Database:
    def __init__(self, settings: Settings):
        url = assert_database_configured(settings)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        self.engine = create_async_engine(
            url, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"}
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            async with session.begin():
                yield session

    async def close(self) -> None:
        await self.engine.dispose()
