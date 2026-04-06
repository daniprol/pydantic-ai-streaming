import json
import pickle

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.run import AgentRunResultEvent

from streaming_chat_api.dbos_streaming import run_dbos_adapter_stream
from streaming_chat_api.services.common import build_adapter
from streaming_chat_api.support_client import FakeSupportClient


@pytest.mark.asyncio
async def test_run_dbos_adapter_stream_emits_vercel_events_and_calls_on_complete(
    chat_request_factory,
    support_agent,
    agent_deps_factory,
) -> None:
    request_body = json.dumps(chat_request_factory('Where is my order?')).encode()
    adapter = build_adapter(request_body, None, support_agent)
    completed: dict[str, str] = {}

    async def on_complete(result) -> None:
        completed['output'] = result.output

    stream = run_dbos_adapter_stream(
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
async def test_run_dbos_adapter_stream_surfaces_agent_errors(chat_request_factory) -> None:
    request_body = json.dumps(chat_request_factory('Trigger an error')).encode()

    class FailingAgent:
        async def run(self, **kwargs):
            raise RuntimeError('stream exploded')

    adapter = build_adapter(request_body, None, FailingAgent())
    stream = run_dbos_adapter_stream(
        adapter=adapter,
        message_history=[],
        deferred_tool_results=None,
        deps=object(),
    )
    body = ''.join([chunk async for chunk in adapter.encode_stream(stream)])

    assert '{"type":"error"' in body
    assert 'stream exploded' in body
    assert 'data: [DONE]' in body


@pytest.mark.asyncio
async def test_run_dbos_adapter_stream_synthesizes_text_when_only_final_result_is_available(
    chat_request_factory,
    agent_deps_factory,
) -> None:
    base_agent = Agent('test', deps_type=type(agent_deps_factory()), output_type=str)

    @base_agent.tool
    async def echo_tool(_: RunContext, value: str) -> str:
        return value

    class ToolEventsOnlyAgent:
        async def run(
            self, *, message_history=None, deps=None, event_stream_handler=None, **kwargs
        ):
            result = None

            async def tool_events():
                nonlocal result
                async for event in base_agent.run_stream_events(
                    message_history=message_history,
                    deps=deps,
                ):
                    if isinstance(event, AgentRunResultEvent):
                        result = event.result
                    elif isinstance(event, FunctionToolCallEvent | FunctionToolResultEvent):
                        yield event

            if event_stream_handler is not None:
                await event_stream_handler(None, tool_events())

            assert result is not None
            return result

    request_body = json.dumps(chat_request_factory('Use the tool and then answer')).encode()
    adapter = build_adapter(request_body, None, ToolEventsOnlyAgent())
    stream = run_dbos_adapter_stream(
        adapter=adapter,
        message_history=[],
        deferred_tool_results=None,
        deps=agent_deps_factory(),
    )
    body = ''.join([chunk async for chunk in adapter.encode_stream(stream)])

    assert '{"type":"tool-output-available"' in body
    assert '{"type":"text-delta"' in body
    assert 'data: [DONE]' in body


def test_agent_dependencies_are_pickleable(agent_deps_factory) -> None:
    pickle.dumps(agent_deps_factory())


@pytest.mark.asyncio
async def test_fake_support_client_returns_deterministic_order_status() -> None:
    support_client = FakeSupportClient()

    first = await support_client.lookup_order_status('order-123')
    second = await support_client.lookup_order_status('order-123')

    assert first == second
