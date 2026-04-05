from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.run import AgentRunResultEvent

from streaming_chat_api.services.common import stream_callback_events


class RunOnlyAgent:
    def __init__(self, inner_agent):
        self._inner_agent = inner_agent

    async def run(
        self,
        *,
        message_history=None,
        deferred_tool_results=None,
        deps=None,
        **kwargs,
    ):
        result = None

        async def event_stream():
            nonlocal result
            async for event in self._inner_agent.run_stream_events(
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                deps=deps,
            ):
                if isinstance(event, AgentRunResultEvent):
                    result = event.result
                else:
                    yield event

        await stream_callback_events(None, event_stream())
        assert result is not None
        return result


class RunOnlyToolEventsAgent(RunOnlyAgent):
    async def run(
        self,
        *,
        message_history=None,
        deferred_tool_results=None,
        deps=None,
        **kwargs,
    ):
        result = None

        async def event_stream():
            nonlocal result
            async for event in self._inner_agent.run_stream_events(
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                deps=deps,
            ):
                if isinstance(event, AgentRunResultEvent):
                    result = event.result
                elif isinstance(event, FunctionToolCallEvent | FunctionToolResultEvent):
                    yield event

        await stream_callback_events(None, event_stream())
        assert result is not None
        return result


async def test_absurd_flow_streams_vercel_events_and_persists_messages(
    api_client,
    app,
    chat_request_factory,
) -> None:
    app.state.resources.agents.absurd = RunOnlyAgent(app.state.resources.agents.basic)
    create_response = await api_client.post('/api/v1/flows/absurd/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/absurd/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Check the Absurd flow'),
    )
    messages = await api_client.get(
        f'/api/v1/flows/absurd/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert response.headers['content-type'].startswith('text/event-stream')
    assert '{"type":"tool-output-available"' in response.text
    assert '{"type":"text-delta"' in response.text
    assert 'data: [DONE]' in response.text
    assert [message['role'] for message in messages.json()['messages']] == [
        'user',
        'assistant',
        'assistant',
    ]


async def test_absurd_flow_streams_final_text_when_only_tool_events_are_emitted(
    api_client,
    app,
    chat_request_factory,
) -> None:
    app.state.resources.agents.absurd = RunOnlyToolEventsAgent(app.state.resources.agents.basic)
    create_response = await api_client.post('/api/v1/flows/absurd/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/absurd/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Check the fallback text stream'),
    )

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert '{"type":"tool-output-available"' in response.text
    assert '{"type":"text-delta"' in response.text
    assert 'https://example.com/help/streaming-delays' in response.text
