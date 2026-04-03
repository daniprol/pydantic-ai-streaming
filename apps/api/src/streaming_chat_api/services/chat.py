from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelRequest
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai._event_stream import VERCEL_AI_DSP_HEADERS
from pydantic_ai.ui.vercel_ai.request_types import UIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.agents.registry import AgentDependencies
from streaming_chat_api.models.entities import FlowType
from streaming_chat_api.repositories.chat import ChatRepository
from streaming_chat_api.schemas.chat import (
    ChatRequestEnvelope,
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationMessagesResponse,
    ConversationSummary,
)
from streaming_chat_api.schemas.pagination import OffsetPaginationParams
from streaming_chat_api.services.runtime import AppResources


def _serialize_model_messages(messages: Sequence[ModelMessage]) -> list[dict[str, Any]]:
    return ModelMessagesTypeAdapter.dump_python(messages, mode='json')


def _deserialize_model_messages(raw_messages: Sequence[dict[str, Any]]) -> list[ModelMessage]:
    if not raw_messages:
        return []
    return ModelMessagesTypeAdapter.validate_python(list(raw_messages))


def _preview_from_message(message: UIMessage) -> str:
    for part in message.parts:
        text = getattr(part, 'text', None)
        if text:
            return text.strip()[:120]
    return 'New conversation'


def _build_deferred_tool_results(payload: ChatRequestEnvelope) -> DeferredToolResults | None:
    if payload.deferred_tool_results is None:
        return None
    return DeferredToolResults(
        calls=payload.deferred_tool_results.calls,
        approvals=payload.deferred_tool_results.approvals,
    )


def _latest_user_message(messages: Sequence[UIMessage]) -> UIMessage | None:
    for message in reversed(messages):
        if message.role == 'user':
            return message
    return None


@dataclass(slots=True)
class ChatFlowRunner:
    flow_type: FlowType
    agent: Any
    replay_enabled: bool = False

    async def stream(
        self,
        *,
        request: Request,
        db: AsyncSession,
        resources: AppResources,
        conversation_id: UUID,
    ) -> Response:
        repository = ChatRepository(db)
        try:
            payload = ChatRequestEnvelope.model_validate(await request.json())
            ui_messages = [UIMessage.model_validate(message) for message in payload.messages]
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        deferred_tool_results = _build_deferred_tool_results(payload)
        new_message = (
            _latest_user_message(ui_messages) if payload.trigger == 'submit-message' else None
        )
        if (
            new_message is None
            and deferred_tool_results is None
            and payload.trigger != 'regenerate-message'
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Request must include a new user message, a regenerate trigger, or deferred tool results.',
            )

        conversation = await repository.get_conversation(conversation_id, self.flow_type)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Conversation not found',
            )
        thread = await repository.get_or_create_thread(conversation.id, self.flow_type)

        history_rows = await repository.list_messages(conversation.id)
        history = _deserialize_model_messages(repository.flatten_model_messages(history_rows))

        if new_message is not None:
            incoming_model_messages = VercelAIAdapter.load_messages([new_message])
            next_sequence = await repository.next_sequence(conversation.id)
            preview = _preview_from_message(new_message)
            await repository.append_message(
                conversation_id=conversation.id,
                role=new_message.role,
                sequence=next_sequence,
                ui_message_json=new_message.model_dump(mode='json'),
                model_messages_json=_serialize_model_messages(incoming_model_messages),
            )
            await repository.update_conversation_preview(
                conversation,
                title=preview,
                preview=preview,
            )
        await repository.update_thread_metadata(
            thread,
            task_queue=resources.settings.temporal.task_queue
            if self.flow_type == FlowType.TEMPORAL
            else None,
            dbos_workflow_id=str(conversation.id)
            if self.flow_type in {FlowType.DBOS, FlowType.DBOS_REPLAY}
            else None,
            workflow_id=str(conversation.id) if self.flow_type == FlowType.TEMPORAL else None,
            replay_id=str(conversation.id) if self.replay_enabled else None,
            metadata_json={'flow_type': self.flow_type.value},
        )
        if self.replay_enabled:
            await repository.set_active_replay_id(conversation, str(conversation.id))
        await db.commit()

        deps = AgentDependencies(
            conversation_id=str(conversation.id),
            flow_type=self.flow_type.value,
            support_client=resources.support_client,
        )

        try:
            adapter = await VercelAIAdapter.from_request(request, agent=self.agent)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

        async def on_complete(result: AgentRunResult[str]):
            await _persist_completion(
                db=db,
                conversation_id=conversation.id,
                flow_type=self.flow_type,
                repository=repository,
                result=result,
                replay_enabled=self.replay_enabled,
            )

        stream = adapter.run_stream(
            message_history=history,
            deferred_tool_results=deferred_tool_results,
            deps=deps,
            on_complete=on_complete,
        )

        if self.replay_enabled:
            encoded_stream = adapter.encode_stream(stream)
            headers = dict(VERCEL_AI_DSP_HEADERS)
            return StreamingResponse(
                resources.replay_broker.live_stream(str(conversation.id), encoded_stream),
                media_type='text/event-stream',
                headers=headers,
            )

        return adapter.streaming_response(stream)


async def _persist_completion(
    *,
    db: AsyncSession,
    conversation_id: UUID,
    flow_type: FlowType,
    repository: ChatRepository,
    result: AgentRunResult[str],
    replay_enabled: bool,
) -> None:
    conversation = await repository.get_conversation(conversation_id, flow_type)
    if conversation is None:
        return

    new_messages = result.new_messages()
    assistant_messages = list(new_messages)
    if assistant_messages and isinstance(assistant_messages[0], ModelRequest):
        assistant_messages = assistant_messages[1:]

    if assistant_messages:
        ui_messages = VercelAIAdapter.dump_messages(assistant_messages)
        assistant_ui_messages = [message for message in ui_messages if message.role == 'assistant']
        if assistant_ui_messages:
            next_sequence = await repository.next_sequence(conversation_id)
            first_assistant = assistant_ui_messages[0]
            preview = _preview_from_message(first_assistant)
            await repository.append_message(
                conversation_id=conversation_id,
                role='assistant',
                sequence=next_sequence,
                ui_message_json=first_assistant.model_dump(mode='json'),
                model_messages_json=_serialize_model_messages(assistant_messages),
            )
            await repository.update_conversation_preview(conversation, title=None, preview=preview)

    if replay_enabled:
        await repository.set_active_replay_id(conversation, None)
    await db.commit()


class ChatService:
    def __init__(self, resources: AppResources):
        self.resources = resources
        self.runners = {
            FlowType.BASIC: ChatFlowRunner(flow_type=FlowType.BASIC, agent=resources.agents.basic),
            FlowType.DBOS: ChatFlowRunner(flow_type=FlowType.DBOS, agent=resources.agents.dbos),
            FlowType.TEMPORAL: ChatFlowRunner(
                flow_type=FlowType.TEMPORAL, agent=resources.agents.temporal
            ),
            FlowType.DBOS_REPLAY: ChatFlowRunner(
                flow_type=FlowType.DBOS_REPLAY,
                agent=resources.agents.dbos_replay,
                replay_enabled=True,
            ),
        }

    async def list_conversations(
        self,
        *,
        db: AsyncSession,
        flow_type: FlowType,
        pagination: OffsetPaginationParams,
    ) -> ConversationListResponse:
        repository = ChatRepository(db)
        conversations, total = await repository.list_conversations(
            flow_type=flow_type,
            skip=pagination.skip,
            limit=pagination.limit,
        )
        return ConversationListResponse(
            items=[
                ConversationSummary.model_validate(conversation, from_attributes=True)
                for conversation in conversations
            ],
            skip=pagination.skip,
            limit=pagination.limit,
            total=total,
        )

    async def create_conversation(
        self,
        *,
        db: AsyncSession,
        flow_type: FlowType,
    ) -> ConversationCreateResponse:
        repository = ChatRepository(db)
        chat_session = await repository.get_or_create_default_session()
        conversation = await repository.get_or_create_conversation(
            session_id=chat_session.id,
            conversation_id=uuid4(),
            flow_type=flow_type,
            title=None,
            preview=None,
        )
        await db.commit()
        return ConversationCreateResponse(
            conversation=ConversationSummary.model_validate(conversation, from_attributes=True)
        )

    async def delete_conversation(
        self,
        *,
        db: AsyncSession,
        flow_type: FlowType,
        conversation_id: UUID,
    ) -> bool:
        repository = ChatRepository(db)
        deleted = await repository.delete_conversation(conversation_id, flow_type)
        if deleted:
            await db.commit()
        return deleted

    async def get_messages(
        self,
        *,
        db: AsyncSession,
        flow_type: FlowType,
        conversation_id: UUID,
    ) -> ConversationMessagesResponse:
        repository = ChatRepository(db)
        conversation = await repository.get_conversation(conversation_id, flow_type)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Conversation not found',
            )
        messages = await repository.list_messages(conversation_id)
        return ConversationMessagesResponse(
            conversation_id=conversation_id,
            flow_type=flow_type,
            active_replay_id=conversation.active_replay_id,
            messages=[message.ui_message_json for message in messages],
        )

    async def stream_chat(
        self,
        *,
        db: AsyncSession,
        request: Request,
        flow_type: FlowType,
        conversation_id: UUID,
    ) -> Response:
        return await self.runners[flow_type].stream(
            request=request,
            db=db,
            resources=self.resources,
            conversation_id=conversation_id,
        )
