from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.resources import AppResources
from streaming_chat_api.schemas import OffsetPaginationParams


async def get_last_event_id(
    q: Annotated[str | None, Query(alias='last_event_id')] = None,
    h: Annotated[str | None, Header(alias='last-event-id')] = None,
) -> str | None:
    return q or h


def get_resources(request: Request) -> AppResources:
    return request.app.state.resources


async def get_db_session(
    resources: Annotated[AppResources, Depends(get_resources)],
) -> AsyncIterator[AsyncSession]:
    async with resources.session_factory() as session:
        yield session


ResourcesDep = Annotated[AppResources, Depends(get_resources)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
PaginationDep = Annotated[OffsetPaginationParams, Depends()]
LastEventIdDep = Annotated[str | None, Depends(get_last_event_id)]
