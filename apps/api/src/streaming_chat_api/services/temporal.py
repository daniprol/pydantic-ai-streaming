from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.common import SearchAttributeKey, SearchAttributePair, TypedSearchAttributes

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
    build_create_response,
    build_list_response,
    build_messages_response,
    build_replay_stream_response,
    create_replay_id,
    get_required_conversation,
    load_message_history,
    parse_chat_request,
    serialize_model_messages,
)
from streaming_chat_api.temporal_workflow import (
    SupportWorkflow,
    build_temporal_workflow_id,
    build_temporal_workflow_input,
)


FLOW_TYPE = FlowType.TEMPORAL
CONVERSATION_ID_SEARCH_ATTRIBUTE = SearchAttributeKey.for_keyword('ConversationId')
MODEL_NAME_SEARCH_ATTRIBUTE = SearchAttributeKey.for_keyword('ModelName')
FLOW_TYPE_SEARCH_ATTRIBUTE = SearchAttributeKey.for_keyword('FlowType')
CONVERSATION_ID_MEMO_KEY = 'conversation_id'
MODEL_NAME_MEMO_KEY = 'model_name'
FLOW_TYPE_MEMO_KEY = 'flow_type'


def build_temporal_search_attributes(
    *,
    conversation_id: str,
    model_name: str,
) -> TypedSearchAttributes:
    return TypedSearchAttributes(
        [
            SearchAttributePair(CONVERSATION_ID_SEARCH_ATTRIBUTE, conversation_id),
            SearchAttributePair(MODEL_NAME_SEARCH_ATTRIBUTE, model_name),
            SearchAttributePair(FLOW_TYPE_SEARCH_ATTRIBUTE, FLOW_TYPE.value),
        ]
    )


def build_temporal_memo(*, conversation_id: str, model_name: str) -> dict[str, str]:
    return {
        CONVERSATION_ID_MEMO_KEY: conversation_id,
        MODEL_NAME_MEMO_KEY: model_name,
        FLOW_TYPE_MEMO_KEY: FLOW_TYPE.value,
    }


def get_temporal_model_name(resources: AppResources) -> str:
    if resources.settings.use_test_model:
        return 'test'
    return resources.settings.azure_openai_model


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
) -> StreamingResponse:
    repository = ConversationRepository(session)
    request_body = await request.body()
    parsed_request = parse_chat_request(request_body)
    conversation = await get_required_conversation(repository, conversation_id, FLOW_TYPE)
    history = await load_message_history(repository, conversation.id, resources.settings)

    if parsed_request.new_message is not None:
        await append_user_message(repository, conversation, parsed_request.new_message)
    await session.commit()

    if resources.temporal_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Temporal client unavailable',
        )

    replay_id = create_replay_id()
    model_name = get_temporal_model_name(resources)
    adapter = build_adapter(request_body, request.headers.get('accept'), resources.agents.basic)
    workflow_input = build_temporal_workflow_input(
        conversation_id=str(conversation.id),
        replay_id=replay_id,
        request_body=request_body,
        accept=request.headers.get('accept'),
        message_history=serialize_model_messages([*history, *adapter.messages]),
        deferred_tool_results=(
            None
            if parsed_request.deferred_tool_results is None
            else {
                'calls': parsed_request.deferred_tool_results.calls,
                'approvals': parsed_request.deferred_tool_results.approvals,
            }
        ),
    )
    await repository.set_active_replay_id(conversation, replay_id)
    await session.commit()

    try:
        await resources.temporal_client.start_workflow(
            SupportWorkflow.run,
            workflow_input,
            id=build_temporal_workflow_id(str(conversation.id), replay_id),
            task_queue=resources.settings.temporal_task_queue,
            memo=build_temporal_memo(
                conversation_id=str(conversation.id),
                model_name=model_name,
            ),
            search_attributes=build_temporal_search_attributes(
                conversation_id=str(conversation.id),
                model_name=model_name,
            ),
        )
    except Exception:
        await repository.set_active_replay_id(conversation, None)
        await session.commit()
        raise

    return build_replay_stream_response(resources, replay_id)
