from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pathwayai_backend.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        url = settings.async_database_url()
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        if url:
            self.engine = create_async_engine(
                url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
            )
            self.session_factory = async_sessionmaker(
                self.engine, expire_on_commit=False
            )

    @property
    def configured(self) -> bool:
        return self.engine is not None and self.session_factory is not None

    async def session(self) -> AsyncIterator[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError("DATABASE_URL is not configured")
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
