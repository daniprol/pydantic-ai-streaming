import json

import pytest
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai_absurd import AbsurdAgent

from streaming_chat_api.resources import build_agents
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


def test_build_agents_creates_absurd_agent(test_settings) -> None:
    agents = build_agents(test_settings, FakeSupportClient())

    assert isinstance(agents.absurd, AbsurdAgent)
