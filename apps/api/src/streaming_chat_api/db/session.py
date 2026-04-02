from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from streaming_chat_api.config.settings import Settings


def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database.url, echo=settings.database.echo)


def create_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_engine_from_settings(settings)
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
