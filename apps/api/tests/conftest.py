from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import fakeredis.aioredis
import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic_ai.tools import DeferredToolResults
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from streaming_chat_api.agents import AgentDependencies, build_support_agent
from streaming_chat_api.database import Base, create_engine, create_session_factory
from streaming_chat_api.main import create_app
from streaming_chat_api.models import FlowType
from streaming_chat_api.repository import ConversationRepository
from streaming_chat_api.replay import ReplayStreamBroker
from streaming_chat_api.resources import AppResources, ChatAgents
from streaming_chat_api.services.common import (
    build_adapter,
    deserialize_model_messages,
    persist_assistant_messages,
)
from streaming_chat_api.settings import API_ENV_FILE, Settings, get_settings
from streaming_chat_api.support_client import FakeSupportClient


class LocalTemporalClient:
    def __init__(self, resources: AppResources):
        self.resources = resources
        self.started_workflows: list[dict[str, object]] = []

    async def list_namespaces(self) -> None:
        raise RuntimeError('Temporal server is not running in unit tests.')

    async def start_workflow(
        self,
        workflow_run,
        workflow_input,
        *,
        id: str,
        task_queue: str,
        memo=None,
        search_attributes=None,
    ):
        self.started_workflows.append(
            {
                'id': id,
                'task_queue': task_queue,
                'workflow': getattr(workflow_run, '__qualname__', str(workflow_run)),
                'workflow_input': workflow_input,
                'memo': memo,
                'search_attributes': {}
                if search_attributes is None
                else {pair.key.name: pair.value for pair in search_attributes.search_attributes},
            }
        )

        adapter = build_adapter(
            workflow_input.request_body.encode('utf-8'),
            workflow_input.accept,
            self.resources.agents.basic,
        )
        deferred_tool_results = None
        if workflow_input.deferred_tool_results is not None:
            deferred_tool_results = DeferredToolResults(**workflow_input.deferred_tool_results)

        async def on_complete(result):
            async with self.resources.session_factory() as session:
                repository = ConversationRepository(session)
                conversation = await repository.get_conversation(
                    UUID(workflow_input.conversation_id),
                    FlowType.TEMPORAL,
                )
                assert conversation is not None
                await persist_assistant_messages(
                    session=session,
                    repository=repository,
                    conversation=conversation,
                    result=result,
                    clear_active_replay_id=True,
                )

        stream = adapter.run_stream(
            message_history=deserialize_model_messages(workflow_input.message_history),
            deferred_tool_results=deferred_tool_results,
            deps=AgentDependencies(conversation_id=workflow_input.conversation_id),
            on_complete=on_complete,
        )
        self.resources.replay_broker.start_stream(
            workflow_input.replay_id,
            adapter.encode_stream(stream),
        )


def build_settings(**overrides) -> Settings:
    values = {
        'app_env': 'test',
        'app_name': 'streaming-chat-api-test',
        'app_cors_origins': ['http://localhost:5173'],
        'redis_url': 'redis://unused',
        'use_test_model': True,
        **overrides,
    }
    return Settings(**values)


async def build_test_resources(settings: Settings) -> AsyncIterator[AppResources]:
    engine: AsyncEngine = create_engine(settings)
    session_factory = create_session_factory(engine)
    attempts = 10 if settings.database_url.startswith('postgresql') else 1
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
                await connection.run_sync(Base.metadata.create_all)
            break
        except Exception:
            if attempt == attempts:
                raise
            await asyncio.sleep(1)

    http_client = httpx.AsyncClient()
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    support_client = FakeSupportClient()
    support_agent = build_support_agent(settings, support_client)
    resources = AppResources(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        redis=fake_redis,
        temporal_client=None,
        support_client=support_client,
        agents=ChatAgents(
            basic=support_agent,
            dbos=support_agent,
            dbos_replay=support_agent,
        ),
        replay_broker=ReplayStreamBroker(fake_redis, settings),
        started_at=datetime.now(timezone.utc),
        dbos_initialized=False,
    )
    resources.temporal_client = LocalTemporalClient(resources)

    try:
        yield resources
    finally:
        await fake_redis.aclose()
        await http_client.aclose()
        await engine.dispose()


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / 'test.db'
    return build_settings(database_url=f'sqlite+aiosqlite:///{database_path}')


@pytest.fixture
def llm_settings() -> Settings:
    get_settings.cache_clear()
    return Settings()


@pytest.fixture
def real_test_settings(tmp_path: Path, llm_settings: Settings) -> Settings:
    if llm_settings.use_test_model or not llm_settings.llm_configured:
        pytest.skip('Real LLM settings are not configured in apps/api/.env')

    database_path = tmp_path / 'real-llm.db'
    return llm_settings.model_copy(
        update={
            'app_env': 'test',
            'app_name': 'streaming-chat-api-real-llm-test',
            'app_cors_origins': ['http://localhost:5173'],
            'database_url': f'sqlite+aiosqlite:///{database_path}',
            'redis_url': 'redis://unused',
        }
    )


@pytest.fixture(scope='session')
def docker_compose_file(pytestconfig) -> str:
    return str(Path(pytestconfig.rootdir) / 'tests' / 'docker-compose.yml')


@pytest.fixture(scope='session')
def docker_compose_project_name() -> str:
    return 'streaming-chat-api-tests'


@pytest.fixture(scope='session')
def docker_setup() -> list[str]:
    return ['down -v', 'up --build --wait']


@pytest.fixture
async def resources(test_settings: Settings) -> AsyncIterator[AppResources]:
    async for resource_bundle in build_test_resources(test_settings):
        yield resource_bundle


@pytest.fixture
async def real_resources(real_test_settings: Settings) -> AsyncIterator[AppResources]:
    async for resource_bundle in build_test_resources(real_test_settings):
        yield resource_bundle


@pytest.fixture(scope='session')
def postgres_dsn(docker_services) -> str:
    port = docker_services.port_for('postgres', 5432)
    return f'postgresql+asyncpg://postgres:postgres@127.0.0.1:{port}/streaming_chat_test'


@pytest.fixture
def postgres_settings(postgres_dsn: str) -> Settings:
    return build_settings(
        app_name='streaming-chat-api-postgres-test',
        database_url=postgres_dsn,
    )


@pytest.fixture
async def postgres_resources(postgres_settings: Settings) -> AsyncIterator[AppResources]:
    async for resource_bundle in build_test_resources(postgres_settings):
        yield resource_bundle


@pytest.fixture
async def app(resources: AppResources, test_settings: Settings) -> AsyncIterator[FastAPI]:
    get_settings.cache_clear()
    app = create_app(test_settings)

    @asynccontextmanager
    async def test_lifespan(_: FastAPI):
        app.state.resources = resources
        app.state.settings = test_settings
        yield

    app.router.lifespan_context = test_lifespan
    yield app


@pytest.fixture
async def real_app(
    real_resources: AppResources,
    real_test_settings: Settings,
) -> AsyncIterator[FastAPI]:
    get_settings.cache_clear()
    app = create_app(real_test_settings)

    @asynccontextmanager
    async def test_lifespan(_: FastAPI):
        app.state.resources = real_resources
        app.state.settings = real_test_settings
        yield

    app.router.lifespan_context = test_lifespan
    yield app


@pytest.fixture
async def postgres_app(
    postgres_resources: AppResources,
    postgres_settings: Settings,
) -> AsyncIterator[FastAPI]:
    get_settings.cache_clear()
    app = create_app(postgres_settings)

    @asynccontextmanager
    async def test_lifespan(_: FastAPI):
        app.state.resources = postgres_resources
        app.state.settings = postgres_settings
        yield

    app.router.lifespan_context = test_lifespan
    yield app


@pytest.fixture
async def db_session(resources: AppResources) -> AsyncIterator[AsyncSession]:
    async with resources.session_factory() as session:
        yield session


@pytest.fixture
async def postgres_db_session(postgres_resources: AppResources) -> AsyncIterator[AsyncSession]:
    async with postgres_resources.session_factory() as session:
        yield session


@pytest.fixture
async def api_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url='http://testserver') as client:
            yield client


@pytest.fixture
async def real_api_client(real_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with LifespanManager(real_app):
        transport = httpx.ASGITransport(app=real_app)
        async with AsyncClient(transport=transport, base_url='http://testserver') as client:
            yield client


@pytest.fixture
async def postgres_api_client(postgres_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with LifespanManager(postgres_app):
        transport = httpx.ASGITransport(app=postgres_app)
        async with AsyncClient(transport=transport, base_url='http://testserver') as client:
            yield client


@pytest.fixture
def chat_request_factory():
    def factory(
        text: str | None = 'Where is my order?',
        *,
        request_id: str = 'request-1',
        message_id: str = 'message-1',
        trigger: str = 'submit-message',
        deferred_tool_results: dict | None = None,
    ) -> dict:
        body: dict = {
            'trigger': trigger,
            'id': request_id,
            'messages': [],
        }
        if message_id is not None:
            body['messageId'] = message_id
        if text is not None:
            body['messages'] = [
                {
                    'id': message_id,
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': text}],
                }
            ]
        if deferred_tool_results is not None:
            body['deferredToolResults'] = deferred_tool_results
        return body

    return factory


@pytest.fixture
def repository_factory():
    def factory(session: AsyncSession) -> ConversationRepository:
        return ConversationRepository(session)

    return factory


@pytest.fixture
def conversation_factory(repository_factory):
    async def factory(
        session: AsyncSession,
        *,
        flow_type: FlowType = FlowType.BASIC,
        title: str | None = None,
        preview: str | None = None,
        active_replay_id: str | None = None,
    ):
        repository = repository_factory(session)
        conversation = await repository.create_conversation(flow_type)
        if title or preview:
            await repository.update_conversation_preview(
                conversation,
                title=title,
                preview=preview,
            )
        if active_replay_id is not None:
            await repository.set_active_replay_id(conversation, active_replay_id)
        return conversation

    return factory


@pytest.fixture
def message_factory(repository_factory):
    async def factory(
        session: AsyncSession,
        *,
        conversation_id,
        role: str = 'user',
        sequence: int = 1,
        ui_message_json: dict | None = None,
        model_messages_json: list | None = None,
    ):
        repository = repository_factory(session)
        return await repository.append_message(
            conversation_id=conversation_id,
            role=role,
            sequence=sequence,
            ui_message_json=ui_message_json or {'id': str(sequence), 'role': role},
            model_messages_json=model_messages_json or [],
        )

    return factory


@pytest.fixture
def agent_deps_factory(resources: AppResources):
    def factory(*, conversation_id: str = 'conversation-1') -> AgentDependencies:
        return AgentDependencies(
            conversation_id=conversation_id,
        )

    return factory


@pytest.fixture
def support_agent(test_settings: Settings):
    return build_support_agent(test_settings)


@pytest.fixture
def real_support_agent(llm_settings: Settings):
    if llm_settings.use_test_model or not llm_settings.llm_configured:
        pytest.skip('Real LLM settings are not configured in apps/api/.env')
    return build_support_agent(llm_settings)


__all__ = ['API_ENV_FILE', 'build_settings']
