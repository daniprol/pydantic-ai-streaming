from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from pydantic_ai.messages import (
    AgentStreamEvent,
    ModelMessage,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

from streaming_chat_api.agents import AgentDependencies


@dataclass(slots=True)
class _StreamFailure:
    error: Exception


_STREAM_COMPLETE = object()
_dbos_stream_queue: ContextVar[
    asyncio.Queue[AgentStreamEvent | AgentRunResultEvent[str] | _StreamFailure | object] | None
] = ContextVar('dbos_stream_queue', default=None)


async def stream_dbos_events(_: Any, event_stream: Any) -> None:
    queue = _dbos_stream_queue.get()
    if queue is None:  # pragma: no cover - indicates incorrect bridge setup
        raise RuntimeError('DBOS event stream queue is not configured.')

    async for event in event_stream:
        await queue.put(event)


def _has_text_content(event: AgentStreamEvent) -> bool:
    if isinstance(event, PartStartEvent | PartEndEvent):
        return isinstance(event.part, TextPart) and bool(event.part.content)
    if isinstance(event, PartDeltaEvent):
        return isinstance(event.delta, TextPartDelta) and bool(event.delta.content_delta)
    return False


def run_dbos_adapter_stream(
    *,
    adapter: VercelAIAdapter,
    message_history: Sequence[ModelMessage] | None,
    deferred_tool_results: DeferredToolResults | None,
    deps: AgentDependencies,
    on_complete: Any = None,
):
    # DBOS exposes streaming via an event-stream handler callback, while the Vercel
    # adapter expects an async iterator. The queue bridges those two interfaces and
    # keeps a little buffering/backpressure between the workflow and the HTTP stream.
    queue: asyncio.Queue[AgentStreamEvent | AgentRunResultEvent[str] | _StreamFailure | object] = (
        asyncio.Queue(maxsize=128)
    )
    all_messages = [*(message_history or []), *adapter.messages]

    async def run_agent() -> None:
        token = _dbos_stream_queue.set(queue)
        try:
            result = await adapter.agent.run(
                message_history=all_messages,
                deferred_tool_results=deferred_tool_results,
                deps=deps,
                event_stream_handler=stream_dbos_events,
            )
            await queue.put(AgentRunResultEvent(result))
        except Exception as exc:
            await queue.put(_StreamFailure(exc))
        finally:
            _dbos_stream_queue.reset(token)
            await queue.put(_STREAM_COMPLETE)

    async def native_stream():
        task = asyncio.create_task(run_agent())
        saw_text_content = False
        try:
            # Drain events until the workflow finishes, then hand the native event
            # stream back to the Vercel adapter for protocol-specific encoding.
            while True:
                item = await queue.get()
                if item is _STREAM_COMPLETE:
                    break
                if isinstance(item, _StreamFailure):
                    raise item.error
                if isinstance(item, AgentRunResultEvent):
                    if (
                        not saw_text_content
                        and isinstance(item.result.output, str)
                        and item.result.output
                    ):
                        text_part = TextPart(content=item.result.output)
                        yield PartStartEvent(index=0, part=text_part)
                        yield PartEndEvent(index=0, part=text_part)
                        saw_text_content = True
                    yield item
                    continue
                saw_text_content = saw_text_content or _has_text_content(item)
                yield item
            await task
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return adapter.transform_stream(native_stream(), on_complete=on_complete)
