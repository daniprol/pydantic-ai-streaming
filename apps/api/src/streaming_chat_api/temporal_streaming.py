from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_ai.messages import (
    AgentStreamEvent,
    BuiltinToolCallEvent,
    BuiltinToolResultEvent,
    FinalResultEvent,
    FunctionToolCallEvent,
    PartStartEvent,
)
from pydantic_ai.tools import RunContext
from pydantic_ai.ui.vercel_ai import VercelAIAdapter, VercelAIEventStream

from streaming_chat_api.agents import AgentDependencies
from streaming_chat_api.services.common import get_required_temporal_metadata


@dataclass(slots=True)
class _ReplayPublisherState:
    event_stream: VercelAIEventStream
    started: bool = False


_publisher_locks: dict[str, asyncio.Lock] = {}
_publisher_states: dict[str, _ReplayPublisherState] = {}


def _get_lock(replay_id: str) -> asyncio.Lock:
    lock = _publisher_locks.get(replay_id)
    if lock is None:
        lock = asyncio.Lock()
        _publisher_locks[replay_id] = lock
    return lock


def _get_or_create_state(
    *,
    replay_id: str,
    request_body: str,
    accept: str | None,
) -> _ReplayPublisherState:
    state = _publisher_states.get(replay_id)
    if state is None:
        state = _ReplayPublisherState(
            event_stream=VercelAIEventStream(
                run_input=VercelAIAdapter.build_run_input(request_body.encode('utf-8')),
                accept=accept,
            )
        )
        _publisher_states[replay_id] = state
    return state


async def _append_chunks(replay_id: str, encoded_chunks: list[str]) -> None:
    if not encoded_chunks:
        return
    from streaming_chat_api.temporal_runtime import get_temporal_worker_runtime

    runtime = get_temporal_worker_runtime()
    for chunk in encoded_chunks:
        await runtime.replay_broker.append_chunk(replay_id, chunk)


async def stream_temporal_events(
    ctx: RunContext[AgentDependencies],
    event_stream: object,
) -> None:
    replay_id, request_body, accept = get_required_temporal_metadata(ctx)
    async for event in event_stream:
        await publish_temporal_event(
            replay_id=replay_id,
            request_body=request_body,
            accept=accept,
            event=event,
        )


async def publish_temporal_event(
    *,
    replay_id: str,
    request_body: str,
    accept: str | None,
    event: AgentStreamEvent,
) -> None:
    async with _get_lock(replay_id):
        state = _get_or_create_state(replay_id=replay_id, request_body=request_body, accept=accept)
        chunks: list[str] = []

        if not state.started:
            chunks.extend(
                [
                    state.event_stream.encode_event(chunk)
                    async for chunk in state.event_stream.before_stream()
                ]
            )
            state.started = True

        if isinstance(event, PartStartEvent):
            chunks.extend(
                [
                    state.event_stream.encode_event(chunk)
                    async for chunk in state.event_stream._turn_to('response')
                ]
            )
        elif isinstance(event, FunctionToolCallEvent):
            chunks.extend(
                [
                    state.event_stream.encode_event(chunk)
                    async for chunk in state.event_stream._turn_to('request')
                ]
            )
        elif isinstance(event, FinalResultEvent):
            state.event_stream._final_result_event = event

        if not isinstance(event, BuiltinToolCallEvent | BuiltinToolResultEvent):
            chunks.extend(
                [
                    state.event_stream.encode_event(chunk)
                    async for chunk in state.event_stream.handle_event(event)
                ]
            )

        await _append_chunks(replay_id, chunks)


async def finish_temporal_stream(
    *,
    replay_id: str,
    request_body: str,
    accept: str | None,
) -> None:
    async with _get_lock(replay_id):
        state = _get_or_create_state(replay_id=replay_id, request_body=request_body, accept=accept)
        chunks: list[str] = []

        if not state.started:
            chunks.extend(
                [
                    state.event_stream.encode_event(chunk)
                    async for chunk in state.event_stream.before_stream()
                ]
            )
            state.started = True

        chunks.extend(
            [
                state.event_stream.encode_event(chunk)
                async for chunk in state.event_stream._turn_to(None)
            ]
        )
        chunks.extend(
            [
                state.event_stream.encode_event(chunk)
                async for chunk in state.event_stream.after_stream()
            ]
        )
        await _append_chunks(replay_id, chunks)

        from streaming_chat_api.temporal_runtime import get_temporal_worker_runtime

        runtime = get_temporal_worker_runtime()
        await runtime.replay_broker.append_complete(replay_id)
        _cleanup_replay_state(replay_id)


async def fail_temporal_stream(
    *,
    replay_id: str,
    request_body: str,
    accept: str | None,
    error_text: str,
) -> None:
    async with _get_lock(replay_id):
        state = _get_or_create_state(replay_id=replay_id, request_body=request_body, accept=accept)
        chunks: list[str] = []

        if not state.started:
            chunks.extend(
                [
                    state.event_stream.encode_event(chunk)
                    async for chunk in state.event_stream.before_stream()
                ]
            )
            state.started = True

        chunks.extend(
            [
                state.event_stream.encode_event(chunk)
                async for chunk in state.event_stream.on_error(RuntimeError(error_text))
            ]
        )
        chunks.extend(
            [
                state.event_stream.encode_event(chunk)
                async for chunk in state.event_stream._turn_to(None)
            ]
        )
        chunks.extend(
            [
                state.event_stream.encode_event(chunk)
                async for chunk in state.event_stream.after_stream()
            ]
        )
        await _append_chunks(replay_id, chunks)

        from streaming_chat_api.temporal_runtime import get_temporal_worker_runtime

        runtime = get_temporal_worker_runtime()
        await runtime.replay_broker.append_complete(replay_id)
        _cleanup_replay_state(replay_id)


def _cleanup_replay_state(replay_id: str) -> None:
    _publisher_states.pop(replay_id, None)
    _publisher_locks.pop(replay_id, None)
