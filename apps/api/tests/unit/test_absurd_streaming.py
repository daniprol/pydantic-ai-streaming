import json

import pytest
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai_absurd import AbsurdAgent
from sqlalchemy.ext.asyncio import create_async_engine

from streaming_chat_api.database import create_session_factory
from streaming_chat_api.resources import build_agents
from streaming_chat_api.services.absurd import ensure_absurd_queue
from streaming_chat_api.services.common import (
    build_adapter,
    run_absurd_adapter_stream,
    stream_callback_events,
)
from streaming_chat_api.support_client import FakeSupportClient


@pytest.mark.asyncio
async def test_run_absurd_adapter_stream_emits_vercel_events_and_calls_on_complete(
    chat_request_factory,
    support_agent,
    agent_deps_factory,
) -> None:
    request_body = json.dumps(chat_request_factory('Where is my order?')).encode()
    adapter = build_adapter(request_body, None, support_agent)
    completed: dict[str, str] = {}

    async def on_complete(result) -> None:
        completed['output'] = result.output

    class CallbackRunOnlyAgent:
        async def run(self, *, message_history=None, deps=None, **kwargs):
            result = None

            async def events():
                nonlocal result
                async for event in support_agent.run_stream_events(
                    message_history=message_history,
                    deps=deps,
                ):
                    if isinstance(event, AgentRunResultEvent):
                        result = event.result
                    else:
                        yield event

            await stream_callback_events(None, events())
            assert result is not None
            return result

    adapter.agent = CallbackRunOnlyAgent()
    stream = run_absurd_adapter_stream(
        adapter=adapter,
        message_history=[],
        deferred_tool_results=None,
        deps=agent_deps_factory(),
        on_complete=on_complete,
    )
    body = ''.join([chunk async for chunk in adapter.encode_stream(stream)])

    assert '{"type":"tool-output-available"' in body
    assert '{"type":"text-delta"' in body
    assert 'data: [DONE]' in body
    assert completed['output']


@pytest.mark.asyncio
async def test_build_agents_creates_absurd_agent_with_worker_safe_callback(test_settings) -> None:
    engine = create_async_engine(test_settings.database_url)
    session_factory = create_session_factory(engine)
    agents = build_agents(test_settings, FakeSupportClient(), session_factory)

    try:
        assert isinstance(agents.absurd, AbsurdAgent)
        assert agents.absurd.on_complete is not None
    finally:
        await engine.dispose()


class FakeAbsurdApp:
    def __init__(self, queues: list[str] | None = None, *, fail_create_once: bool = False) -> None:
        self.queues = list(queues or [])
        self.list_calls = 0
        self.create_calls = 0
        self.fail_create_once = fail_create_once

    async def list_queues(self) -> list[str]:
        self.list_calls += 1
        return list(self.queues)

    async def create_queue(self, queue_name: str) -> None:
        self.create_calls += 1
        if self.fail_create_once:
            self.fail_create_once = False
            self.queues.append(queue_name)
            raise RuntimeError('queue already exists')
        self.queues.append(queue_name)


@pytest.mark.asyncio
async def test_ensure_absurd_queue_noops_when_disabled() -> None:
    app = FakeAbsurdApp()

    await ensure_absurd_queue(
        app,
        queue_name='streaming-chat-api-absurd',
        create_if_not_exists=False,
    )

    assert app.list_calls == 0
    assert app.create_calls == 0


@pytest.mark.asyncio
async def test_ensure_absurd_queue_creates_missing_queue() -> None:
    app = FakeAbsurdApp()

    await ensure_absurd_queue(
        app,
        queue_name='streaming-chat-api-absurd',
        create_if_not_exists=True,
    )

    assert app.queues == ['streaming-chat-api-absurd']
    assert app.create_calls == 1


@pytest.mark.asyncio
async def test_ensure_absurd_queue_skips_existing_queue() -> None:
    app = FakeAbsurdApp(['streaming-chat-api-absurd'])

    await ensure_absurd_queue(
        app,
        queue_name='streaming-chat-api-absurd',
        create_if_not_exists=True,
    )

    assert app.create_calls == 0


@pytest.mark.asyncio
async def test_ensure_absurd_queue_tolerates_concurrent_create_race() -> None:
    app = FakeAbsurdApp(fail_create_once=True)

    await ensure_absurd_queue(
        app,
        queue_name='streaming-chat-api-absurd',
        create_if_not_exists=True,
    )

    assert app.queues == ['streaming-chat-api-absurd']
    assert app.create_calls == 1
