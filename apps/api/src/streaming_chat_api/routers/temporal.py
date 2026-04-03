from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from streaming_chat_api.dependencies import PaginationDep, ResourcesDep, SessionDep
from streaming_chat_api.schemas import (
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationMessagesResponse,
)
from streaming_chat_api.services import temporal as temporal_service


router = APIRouter(prefix='/flows/temporal', tags=['temporal'])


@router.get('/conversations', response_model=ConversationListResponse)
async def list_conversations(
    pagination: PaginationDep,
    session: SessionDep,
) -> ConversationListResponse:
    return await temporal_service.list_conversations(session, pagination)


@router.post('/conversations', response_model=ConversationCreateResponse, status_code=201)
async def create_conversation(session: SessionDep) -> ConversationCreateResponse:
    return await temporal_service.create_conversation(session)


@router.delete('/conversations/{conversation_id}', status_code=204)
async def delete_conversation(conversation_id: UUID, session: SessionDep) -> None:
    deleted = await temporal_service.delete_conversation(session, conversation_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Conversation not found')


@router.get(
    '/conversations/{conversation_id}/messages', response_model=ConversationMessagesResponse
)
async def get_messages(
    conversation_id: UUID,
    session: SessionDep,
) -> ConversationMessagesResponse:
    return await temporal_service.get_messages(session, conversation_id)


@router.post('/chat')
async def chat(
    request: Request,
    session: SessionDep,
    resources: ResourcesDep,
    conversation_id: UUID = Query(...),
):
    return await temporal_service.stream_chat(
        session=session,
        request=request,
        resources=resources,
        conversation_id=conversation_id,
    )
