from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from absurd_sdk import AsyncAbsurd
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic_ai_absurd import AbsurdAgent, OnCompleteContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from streaming_chat_api.agents import AgentDependencies
from streaming_chat_api.models import FlowType
from streaming_chat_api.repository import ConversationRepository
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
    build_create_response,
    build_list_response,
    build_messages_response,
    get_required_conversation,
    load_message_history,
    parse_chat_request,
    persist_assistant_messages,
    run_absurd_adapter_stream,
)

if TYPE_CHECKING:
    from streaming_chat_api.resources import AppResources


FLOW_TYPE = FlowType.ABSURD
logger = logging.getLogger(__name__)


async def ensure_absurd_queue(
    app: AsyncAbsurd,
    *,
    queue_name: str,
    create_if_not_exists: bool,
) -> None:
    if not create_if_not_exists:
        return

    if queue_name in await app.list_queues():
        return

    try:
        await app.create_queue(queue_name)
        logger.info('Created Absurd queue %s during startup', queue_name)
    except Exception:
        # API and worker can start together; if another process won the race, accept it.
        if queue_name not in await app.list_queues():
            raise


def build_absurd_on_complete(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[OnCompleteContext[AgentDependencies, str]], Awaitable[None]]:
    # Absurd stores task names and JSON payloads, not Python callables. The API process and
    # worker process must therefore both construct the agent with this same callback code.
    async def on_complete(context: OnCompleteContext[AgentDependencies, str]) -> None:
        async with session_factory() as session:
            repository = ConversationRepository(session)
            conversation = await get_required_conversation(
                repository,
                UUID(context.deps.conversation_id),
                FLOW_TYPE,
            )
            await persist_assistant_messages(
                session=session,
                repository=repository,
                conversation=conversation,
                result=context.result,
            )

    return on_complete


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
    history = await load_message_history(repository, conversation.id)

    if parsed_request.new_message is not None:
        await append_user_message(repository, conversation, parsed_request.new_message)
    await session.commit()

    absurd_agent = resources.agents.absurd
    adapter = build_adapter(request_body, request.headers.get('accept'), absurd_agent)
    deps = build_agent_dependencies(resources, conversation)

    fallback_on_complete = None
    if not isinstance(absurd_agent, AbsurdAgent) or absurd_agent.on_complete is None:

        async def fallback_on_complete(result) -> None:
            await persist_assistant_messages(
                session=session,
                repository=repository,
                conversation=conversation,
                result=result,
            )

    stream = run_absurd_adapter_stream(
        adapter=adapter,
        message_history=history,
        deferred_tool_results=parsed_request.deferred_tool_results,
        deps=deps,
        on_complete=fallback_on_complete,
    )
    return adapter.streaming_response(stream)
