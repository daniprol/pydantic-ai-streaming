from __future__ import annotations

from uuid import UUID

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.dependencies.resources import get_db_session, get_resources, get_session_id
from streaming_chat_api.models.entities import FlowType
from streaming_chat_api.schemas.chat import ConversationListResponse, ConversationMessagesResponse
from streaming_chat_api.schemas.pagination import OffsetPaginationParams
from streaming_chat_api.services.chat import ChatService
from streaming_chat_api.services.runtime import AppResources
from streaming_chat_api.ui import replay_stream_response


router = APIRouter(prefix='/api/v1/flows', tags=['flows'])


def get_chat_service(resources: AppResources = Depends(get_resources)) -> ChatService:
    return ChatService(resources)


@router.get('/{flow}/conversations', response_model=ConversationListResponse)
async def list_conversations(
    flow: FlowType,
    pagination: Annotated[OffsetPaginationParams, Depends()],
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service),
) -> ConversationListResponse:
    return await service.list_conversations(
        db=db,
        session_id=session_id,
        flow_type=flow,
        pagination=pagination,
    )


@router.get(
    '/{flow}/conversations/{conversation_id}/messages',
    response_model=ConversationMessagesResponse,
)
async def get_conversation_messages(
    flow: FlowType,
    conversation_id: UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service),
) -> ConversationMessagesResponse:
    return await service.get_messages(
        db=db,
        session_id=session_id,
        flow_type=flow,
        conversation_id=conversation_id,
    )


@router.post('/{flow}/chat')
async def chat(
    flow: FlowType,
    request: Request,
    conversation_id: UUID = Query(...),
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service),
):
    return await service.stream_chat(
        db=db,
        request=request,
        session_id=session_id,
        flow_type=flow,
        conversation_id=conversation_id,
    )


@router.get('/dbos-replay/streams/{replay_id}/replay')
async def replay_stream(
    replay_id: str,
    request: Request,
    resources: AppResources = Depends(get_resources),
):
    last_event_id = request.query_params.get('last_event_id') or request.headers.get(
        'last-event-id'
    )
    return replay_stream_response(resources.replay_broker.replay_stream(replay_id, last_event_id))
