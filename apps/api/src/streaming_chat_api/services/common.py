from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any
from uuid import UUID
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
)
from pydantic_ai.tools import DeferredToolResults, RunContext
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import UIMessage
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.agents import AgentDependencies
from streaming_chat_api.models import Conversation, FlowType
from streaming_chat_api.repository import ConversationRepository
from streaming_chat_api.resources import AppResources
from streaming_chat_api.schemas import (
    ChatRequestEnvelope,
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationMessagesResponse,
    ConversationSummary,
    OffsetPaginationParams,
)
from streaming_chat_api.ui import replay_stream_response


@dataclass(slots=True)
class ParsedChatRequest:
    deferred_tool_results: DeferredToolResults | None
    new_message: UIMessage | None


REPLAY_ID_HEADER = 'x-replay-id'


def serialize_model_messages(messages: Sequence[ModelMessage]) -> list[dict[str, Any]]:
    return ModelMessagesTypeAdapter.dump_python(messages, mode='json')


def deserialize_model_messages(raw_messages: Sequence[dict[str, Any]]) -> list[ModelMessage]:
    if not raw_messages:
        return []
    return ModelMessagesTypeAdapter.validate_python(list(raw_messages))


def preview_from_message(message: UIMessage) -> str:
    for part in message.parts:
        text = getattr(part, 'text', None)
        if text:
            return text.strip()[:120]
    return 'New conversation'


def preview_from_messages(messages: Sequence[UIMessage]) -> str | None:
    for message in reversed(messages):
        preview = preview_from_message(message)
        if preview and preview != 'New conversation':
            return preview
    return None


def build_list_response(
    conversations: list[Conversation],
    total: int,
    pagination: OffsetPaginationParams,
) -> ConversationListResponse:
    return ConversationListResponse(
        items=[ConversationSummary.model_validate(conversation) for conversation in conversations],
        skip=pagination.skip,
        limit=pagination.limit,
        total=total,
    )


def build_create_response(conversation: Conversation) -> ConversationCreateResponse:
    return ConversationCreateResponse(conversation=ConversationSummary.model_validate(conversation))


def build_messages_response(
    conversation: Conversation,
    messages: list[dict],
) -> ConversationMessagesResponse:
    return ConversationMessagesResponse(
        conversation_id=conversation.id,
        flow_type=conversation.flow_type,
        active_replay_id=conversation.active_replay_id,
        messages=messages,
    )


def parse_chat_request(request_body: bytes) -> ParsedChatRequest:
    try:
        payload = ChatRequestEnvelope.model_validate(json.loads(request_body))
        ui_messages = [UIMessage.model_validate(message) for message in payload.messages]
    except JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='Request body must be valid JSON.',
        ) from exc
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    deferred_tool_results = None
    if payload.deferred_tool_results is not None:
        deferred_tool_results = DeferredToolResults(
            calls=payload.deferred_tool_results.calls,
            approvals=payload.deferred_tool_results.approvals,
        )

    new_message = None
    if payload.trigger == 'submit-message':
        for message in reversed(ui_messages):
            if message.role == 'user':
                new_message = message
                break

    if (
        new_message is None
        and deferred_tool_results is None
        and payload.trigger != 'regenerate-message'
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Request must include a new user message, a regenerate trigger, or deferred tool results.',
        )

    return ParsedChatRequest(
        deferred_tool_results=deferred_tool_results,
        new_message=new_message,
    )


async def get_required_conversation(
    repository: ConversationRepository,
    conversation_id: UUID,
    flow_type: FlowType,
) -> Conversation:
    conversation = await repository.get_conversation(conversation_id, flow_type)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Conversation not found',
        )
    return conversation


async def load_message_history(
    repository: ConversationRepository,
    conversation_id: UUID,
) -> list[ModelMessage]:
    history_rows = await repository.list_messages(conversation_id)
    return deserialize_model_messages(repository.flatten_model_messages(history_rows))


async def append_user_message(
    repository: ConversationRepository,
    conversation: Conversation,
    message: UIMessage,
) -> None:
    incoming_model_messages = VercelAIAdapter.load_messages([message])
    next_sequence = await repository.next_sequence(conversation.id)
    preview = preview_from_message(message)
    await repository.append_message(
        conversation_id=conversation.id,
        role=message.role,
        sequence=next_sequence,
        ui_message_json=message.model_dump(mode='json'),
        model_messages_json=serialize_model_messages(incoming_model_messages),
    )
    await repository.update_conversation_preview(
        conversation,
        title=preview,
        preview=preview,
    )


async def persist_assistant_model_messages(
    *,
    session: AsyncSession,
    repository: ConversationRepository,
    conversation: Conversation,
    new_messages: Sequence[ModelMessage],
    clear_active_replay_id: bool = False,
) -> None:
    assistant_messages = list(new_messages)
    if assistant_messages and isinstance(assistant_messages[0], ModelRequest):
        assistant_messages = assistant_messages[1:]

    if assistant_messages:
        ui_messages = VercelAIAdapter.dump_messages(assistant_messages)
        assistant_ui_messages = [message for message in ui_messages if message.role == 'assistant']
        if assistant_ui_messages:
            next_sequence = await repository.next_sequence(conversation.id)
            serialized_assistant_messages = serialize_model_messages(assistant_messages)
            for index, assistant_message in enumerate(assistant_ui_messages):
                await repository.append_message(
                    conversation_id=conversation.id,
                    role='assistant',
                    sequence=next_sequence + index,
                    ui_message_json=assistant_message.model_dump(mode='json'),
                    model_messages_json=serialized_assistant_messages if index == 0 else [],
                )
            preview = preview_from_messages(assistant_ui_messages)
            await repository.update_conversation_preview(
                conversation,
                title=None,
                preview=preview,
            )

    if clear_active_replay_id:
        await repository.set_active_replay_id(conversation, None)
    await session.commit()


async def persist_assistant_messages(
    *,
    session: AsyncSession,
    repository: ConversationRepository,
    conversation: Conversation,
    result: AgentRunResult[str],
    clear_active_replay_id: bool = False,
) -> None:
    await persist_assistant_model_messages(
        session=session,
        repository=repository,
        conversation=conversation,
        new_messages=result.new_messages(),
        clear_active_replay_id=clear_active_replay_id,
    )


def build_agent_dependencies(
    resources: AppResources,
    conversation: Conversation,
) -> AgentDependencies:
    return AgentDependencies(
        conversation_id=str(conversation.id),
    )


def build_adapter(request_body: bytes, accept: str | None, agent: Any) -> VercelAIAdapter:
    try:
        run_input = VercelAIAdapter.build_run_input(request_body)
        return VercelAIAdapter(
            agent=agent,
            run_input=run_input,
            accept=accept,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def create_replay_id() -> str:
    return str(uuid4())


def build_temporal_run_metadata(
    *,
    replay_id: str,
    request_body: bytes,
    accept: str | None,
) -> dict[str, str | None]:
    return {
        'replay_id': replay_id,
        'request_body': request_body.decode('utf-8'),
        'accept': accept,
    }


async def build_replayable_streaming_response(
    *,
    session: AsyncSession,
    repository: ConversationRepository,
    conversation: Conversation,
    resources: AppResources,
    adapter: VercelAIAdapter,
    stream: Any,
    replay_id: str,
) -> StreamingResponse:
    await repository.set_active_replay_id(conversation, replay_id)
    await session.commit()

    resources.replay_broker.start_stream(replay_id, adapter.encode_stream(stream))
    return build_replay_stream_response(resources, replay_id)


def build_replay_stream_response(
    resources: AppResources,
    replay_id: str,
) -> StreamingResponse:
    return replay_stream_response(
        resources.replay_broker.replay_stream(replay_id, None),
        headers={REPLAY_ID_HEADER: replay_id},
    )


def get_required_temporal_metadata(
    ctx: RunContext[AgentDependencies],
) -> tuple[str, str, str | None]:
    metadata = ctx.metadata
    if not isinstance(metadata, dict):  # pragma: no cover - defensive validation
        raise RuntimeError('Temporal run metadata is missing.')

    replay_id = metadata.get('replay_id')
    request_body = metadata.get('request_body')
    accept = metadata.get('accept')
    if not isinstance(replay_id, str) or not isinstance(request_body, str):
        raise RuntimeError('Temporal run metadata is incomplete.')
    if accept is not None and not isinstance(accept, str):
        raise RuntimeError('Temporal Accept header must be a string when provided.')
    return replay_id, request_body, accept
