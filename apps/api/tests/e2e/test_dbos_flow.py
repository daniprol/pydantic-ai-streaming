from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from pydantic_ai.run import AgentRunResultEvent

from streaming_chat_api.e2e_server import build_e2e_app


class RunOnlyAgent:
    def __init__(self, inner_agent):
        self._inner_agent = inner_agent

    async def run(
        self,
        *,
        message_history=None,
        deferred_tool_results=None,
        deps=None,
        event_stream_handler=None,
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

        if event_stream_handler is not None:
            await event_stream_handler(None, event_stream())

        assert result is not None
        return result


async def test_e2e_dbos_route_streams_via_run_only_agent() -> None:
    app = build_e2e_app()

    async with LifespanManager(app):
        app.state.resources.agents.dbos = RunOnlyAgent(app.state.resources.agents.basic)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://testserver') as client:
            create_response = await client.post('/api/v1/flows/dbos/conversations')
            conversation_id = create_response.json()['conversation']['id']

            response = await client.post(
                f'/api/v1/flows/dbos/chat?conversation_id={conversation_id}',
                json={
                    'trigger': 'submit-message',
                    'id': 'request-1',
                    'messageId': 'message-1',
                    'messages': [
                        {
                            'id': 'message-1',
                            'role': 'user',
                            'parts': [{'type': 'text', 'text': 'Check the DBOS e2e flow'}],
                        }
                    ],
                },
            )

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert response.headers['content-type'].startswith('text/event-stream')
    assert '{"type":"text-delta"' in response.text
    assert 'data: [DONE]' in response.text
