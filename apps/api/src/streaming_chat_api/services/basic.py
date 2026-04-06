from __future__ import annotations

from uuid import UUID

from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

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
    build_adapter_request_body,
    build_create_response,
    build_list_response,
    build_messages_response,
    get_required_conversation,
    load_message_history,
    load_pending_tool_call_responses,
    parse_chat_request,
    persist_assistant_messages,
)
from streaming_chat_api.services.hitl import (
    apply_pending_tool_resolutions,
    build_custom_pending_tool_data_part,
    extract_tool_outputs_from_resume_messages,
    merge_deferred_tool_results,
    pending_policy_blocks_new_message,
    raise_pending_conflict,
    validate_and_resolve_pending_tool_results,
)
from pydantic_ai.ui.vercel_ai.response_types import DataChunk


FLOW_TYPE = FlowType.BASIC


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
    pending_tool_calls = await load_pending_tool_call_responses(repository, conversation.id)
    return build_messages_response(
        conversation,
        [message.ui_message_json for message in messages],
        pending_tool_calls,
    )


async def stream_chat(
    *,
    session: AsyncSession,
    request: Request,
    resources: AppResources,
    conversation_id: UUID,
) -> StreamingResponse:
    repository = ConversationRepository(session)
    request_body = await request.body()
    parsed_request = parse_chat_request(request_body)
    conversation = await get_required_conversation(repository, conversation_id, FLOW_TYPE)
    history = await load_message_history(repository, conversation.id)
    unresolved_pending_tool_calls = await repository.list_unresolved_pending_tool_calls(
        conversation.id
    )

    adapter_request_body = build_adapter_request_body(
        request_body,
        parsed_request=parsed_request,
    )
    adapter = build_adapter(
        adapter_request_body,
        request.headers.get('accept'),
        resources.agents.basic,
    )
    resumed_tool_results = extract_tool_outputs_from_resume_messages(parsed_request.resume_messages)
    deferred_tool_results = merge_deferred_tool_results(
        adapter.deferred_tool_results,
        merge_deferred_tool_results(parsed_request.deferred_tool_results, resumed_tool_results),
    )

    if pending_policy_blocks_new_message(
        settings=resources.settings,
        unresolved_pending_tool_calls=unresolved_pending_tool_calls,
        has_new_message=parsed_request.new_message is not None,
        has_deferred_tool_results=deferred_tool_results is not None,
    ):
        raise_pending_conflict(unresolved_pending_tool_calls)

    resolutions = await validate_and_resolve_pending_tool_results(
        repository=repository,
        conversation=conversation,
        deferred_tool_results=deferred_tool_results,
    )

    if parsed_request.new_message is not None:
        await append_user_message(repository, conversation, parsed_request.new_message)
    if resolutions:
        await apply_pending_tool_resolutions(
            repository=repository,
            conversation=conversation,
            resolutions=resolutions,
        )
    await session.commit()

    deps = build_agent_dependencies(resources, conversation)

    async def on_complete(result):
        await persist_assistant_messages(
            session=session,
            repository=repository,
            conversation=conversation,
            result=result,
        )
        if hasattr(result.output, 'calls'):
            for call in result.output.calls:
                pending_tool_call = await repository.get_pending_tool_call_by_tool_call_id(
                    conversation.id,
                    call.tool_call_id,
                )
                if pending_tool_call is None:
                    continue
                yield DataChunk(
                    type='data-hitl-request',
                    id=call.tool_call_id,
                    data=build_custom_pending_tool_data_part(pending_tool_call)['data'],
                )

    stream = adapter.run_stream(
        message_history=history,
        deferred_tool_results=deferred_tool_results,
        deps=deps,
        on_complete=on_complete,
    )
    return adapter.streaming_response(stream)
