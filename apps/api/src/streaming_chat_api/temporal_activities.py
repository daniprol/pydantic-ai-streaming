from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from temporalio import activity

from streaming_chat_api.models import FlowType
from streaming_chat_api.repository import ConversationRepository
from streaming_chat_api.services.common import (
    deserialize_model_messages,
    persist_assistant_model_messages,
)
from streaming_chat_api.temporal_runtime import get_temporal_worker_runtime
from streaming_chat_api.temporal_streaming import fail_temporal_stream, finish_temporal_stream


@dataclass(slots=True)
class PersistRunOutputInput:
    conversation_id: str
    new_messages: list[dict[str, Any]]


@dataclass(slots=True)
class ClearReplayInput:
    conversation_id: str


@dataclass(slots=True)
class FinalizeReplayStreamInput:
    replay_id: str
    request_body: str
    accept: str | None


@dataclass(slots=True)
class FailReplayStreamInput(FinalizeReplayStreamInput):
    error_text: str


async def _get_temporal_conversation(repository: ConversationRepository, conversation_id: str):
    conversation = await repository.get_conversation(UUID(conversation_id), FlowType.TEMPORAL)
    if conversation is None:
        raise ValueError(f'Temporal conversation {conversation_id} was not found.')
    return conversation


@activity.defn(name='streaming_chat.persist_temporal_run_output')
async def persist_temporal_run_output(payload: PersistRunOutputInput) -> None:
    runtime = get_temporal_worker_runtime()
    async with runtime.session_factory() as session:
        repository = ConversationRepository(session)
        conversation = await _get_temporal_conversation(repository, payload.conversation_id)
        await persist_assistant_model_messages(
            session=session,
            repository=repository,
            conversation=conversation,
            settings=runtime.settings,
            new_messages=deserialize_model_messages(payload.new_messages),
            clear_active_replay_id=True,
        )


@activity.defn(name='streaming_chat.clear_temporal_replay')
async def clear_temporal_replay(payload: ClearReplayInput) -> None:
    runtime = get_temporal_worker_runtime()
    async with runtime.session_factory() as session:
        repository = ConversationRepository(session)
        conversation = await _get_temporal_conversation(repository, payload.conversation_id)
        await repository.set_active_replay_id(conversation, None)
        await session.commit()


@activity.defn(name='streaming_chat.finish_temporal_replay_stream')
async def finish_temporal_replay_stream(payload: FinalizeReplayStreamInput) -> None:
    await finish_temporal_stream(
        replay_id=payload.replay_id,
        request_body=payload.request_body,
        accept=payload.accept,
    )


@activity.defn(name='streaming_chat.fail_temporal_replay_stream')
async def fail_temporal_replay_stream(payload: FailReplayStreamInput) -> None:
    await fail_temporal_stream(
        replay_id=payload.replay_id,
        request_body=payload.request_body,
        accept=payload.accept,
        error_text=payload.error_text,
    )
