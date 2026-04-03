from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.services.runtime import AppResources


def get_resources(request: Request) -> AppResources:
    return request.app.state.resources


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    resources: AppResources = request.app.state.resources
    async with resources.session_factory() as session:
        yield session
