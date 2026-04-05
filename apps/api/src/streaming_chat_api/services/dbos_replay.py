from __future__ import annotations

from uuid import UUID

from fastapi import Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.dbos_streaming import run_dbos_adapter_stream
from streaming_chat_api.models import FlowType
from streaming_chat_api.repository import ConversationRepository
from streaming_chat_api.resources import AppResources
from streaming_chat_api.schemas import (
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationMessagesResponse,
    OffsetPaginationParams,
)
from streaming_chat_api.services.common import (
    append_user_message,
    build_adapter,
    build_agent_dependencies,
    create_replay_id,
    build_create_response,
    build_list_response,
    build_messages_response,
    build_replayable_streaming_response,
    get_required_conversation,
    load_message_history,
    parse_chat_request,
    persist_assistant_messages,
)


FLOW_TYPE = FlowType.DBOS_REPLAY


async def list_conversations(
    session: AsyncSession,
    pagination: OffsetPaginationParams,
) -> ConversationListResponse:
    repository = ConversationRepository(session)
    conversations, total = await repository.list_conversations(
        flow_type=FLOW_TYPE,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return build_list_response(conversations, total, pagination)


async def create_conversation(session: AsyncSession) -> ConversationCreateResponse:
    repository = ConversationRepository(session)
    conversation = await repository.create_conversation(FLOW_TYPE)
    await session.commit()
    return build_create_response(conversation)


async def delete_conversation(session: AsyncSession, conversation_id: UUID) -> bool:
    repository = ConversationRepository(session)
    deleted = await repository.delete_conversation(conversation_id, FLOW_TYPE)
    if deleted:
        await session.commit()
    return deleted


async def get_messages(
    session: AsyncSession,
    conversation_id: UUID,
) -> ConversationMessagesResponse:
    repository = ConversationRepository(session)
    conversation = await get_required_conversation(repository, conversation_id, FLOW_TYPE)
    messages = await repository.list_messages(conversation.id)
    return build_messages_response(
        conversation,
        [message.ui_message_json for message in messages],
    )


async def stream_chat(
    *,
    session: AsyncSession,
    request: Request,
    resources: AppResources,
    conversation_id: UUID,
) -> Response:
    repository = ConversationRepository(session)
    request_body = await request.body()
    parsed_request = parse_chat_request(request_body)
    conversation = await get_required_conversation(repository, conversation_id, FLOW_TYPE)
    history = await load_message_history(repository, conversation.id)

    if parsed_request.new_message is not None:
        await append_user_message(repository, conversation, parsed_request.new_message)
    await session.commit()

    adapter = build_adapter(
        request_body, request.headers.get('accept'), resources.agents.dbos_replay
    )
    deps = build_agent_dependencies(resources, conversation)

    async def on_complete(result):
        await persist_assistant_messages(
            session=session,
            repository=repository,
            conversation=conversation,
            result=result,
            clear_active_replay_id=True,
        )

    stream = run_dbos_adapter_stream(
        adapter=adapter,
        message_history=history,
        deferred_tool_results=parsed_request.deferred_tool_results,
        deps=deps,
        on_complete=on_complete,
    )
    replay_id = create_replay_id()
    return await build_replayable_streaming_response(
        session=session,
        repository=repository,
        conversation=conversation,
        resources=resources,
        adapter=adapter,
        stream=stream,
        replay_id=replay_id,
    )
