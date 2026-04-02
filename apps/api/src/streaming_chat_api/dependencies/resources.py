from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.repositories.chat import ChatRepository
from streaming_chat_api.services.runtime import AppResources


def get_resources(request: Request) -> AppResources:
    return request.app.state.resources


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    resources: AppResources = request.app.state.resources
    async with resources.session_factory() as session:
        yield session


def get_session_id(x_session_id: str | None = Header(default=None)) -> str:
    if not x_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Missing X-Session-Id header',
        )
    return x_session_id


def get_chat_repository(session: AsyncSession) -> ChatRepository:
    return ChatRepository(session)
