from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic_ai.run import AgentRunResultEvent

from streaming_chat_api.agents import AgentDependencies
from streaming_chat_api.database import Base
from streaming_chat_api.main import create_app
from streaming_chat_api.resources import AppResources, close_resources, create_resources
from streaming_chat_api.settings import Settings, get_settings
from streaming_chat_api.services.common import _dbos_stream_queue, stream_dbos_events


@pytest.fixture
async def real_dbos_resources(postgres_dsn: str) -> AppResources:
    settings = Settings(
        app_env='test',
        app_name='chat-api-dbos-test',
        app_cors_origins=['http://localhost:5173'],
        database_url=postgres_dsn,
        dbos_system_database_url=postgres_dsn.replace('+asyncpg', ''),
        redis_url='redis://unused',
        use_test_model=True,
    )
    resources = await create_resources(settings)
    async with resources.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield resources
    finally:
        await close_resources(resources)


@pytest.fixture
async def real_dbos_app(real_dbos_resources: AppResources) -> FastAPI:
    get_settings.cache_clear()
    app = create_app(real_dbos_resources.settings)

    @asynccontextmanager
    async def test_lifespan(_: FastAPI):
        app.state.resources = real_dbos_resources
        app.state.settings = real_dbos_resources.settings
        yield

    app.router.lifespan_context = test_lifespan
    return app


@pytest.mark.docker
@pytest.mark.asyncio
async def test_real_dbos_agent_and_route_stream_text_and_tool_events(
    real_dbos_resources: AppResources,
    real_dbos_app: FastAPI,
    chat_request_factory,
) -> None:
    assert real_dbos_resources.dbos_initialized is True

    queue: asyncio.Queue[object] = asyncio.Queue()
    token = _dbos_stream_queue.set(queue)
    try:

        async def run_agent() -> None:
            result = await real_dbos_resources.agents.dbos.run(
                'Where is my order?',
                deps=AgentDependencies(conversation_id='docker-conversation'),
                event_stream_handler=stream_dbos_events,
            )
            await queue.put(AgentRunResultEvent(result))
            await queue.put(None)

        task = asyncio.create_task(run_agent())
        event_types: list[str] = []
        while True:
            item = await queue.get()
            if item is None:
                break
            event_types.append(type(item).__name__)
        await task
    finally:
        _dbos_stream_queue.reset(token)

    assert 'PartStartEvent' in event_types
    assert 'PartDeltaEvent' in event_types
    assert 'FunctionToolCallEvent' in event_types
    assert 'FunctionToolResultEvent' in event_types
    assert event_types[-1] == 'AgentRunResultEvent'

    async with LifespanManager(real_dbos_app):
        transport = httpx.ASGITransport(app=real_dbos_app)
        async with AsyncClient(transport=transport, base_url='http://testserver') as client:
            create_response = await client.post('/api/v1/flows/dbos/conversations')
            conversation_id = create_response.json()['conversation']['id']

            async with client.stream(
                'POST',
                f'/api/v1/flows/dbos/chat?conversation_id={conversation_id}',
                json=chat_request_factory('Where is my order?'),
            ) as response:
                stream_lines = [line async for line in response.aiter_lines() if line]

            messages = await client.get(
                f'/api/v1/flows/dbos/conversations/{conversation_id}/messages'
            )

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert response.headers['content-type'].startswith('text/event-stream')
    assert any('"type":"tool-output-available"' in line for line in stream_lines)
    assert any('"type":"text-delta"' in line for line in stream_lines)
    assert any('https://example.com/help/streaming-delays' in line for line in stream_lines)
    assert stream_lines[-1] == 'data: [DONE]'
    assert [message['role'] for message in messages.json()['messages']] == [
        'user',
        'assistant',
        'assistant',
    ]
