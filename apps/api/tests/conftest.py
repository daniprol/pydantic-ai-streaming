from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import fakeredis.aioredis
import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from streaming_chat_api.agents.registry import AgentDependencies, build_support_agent
from streaming_chat_api.clients.fake_support import FakeSupportClient
from streaming_chat_api.config.settings import Settings, get_settings
from streaming_chat_api.db.base import Base
from streaming_chat_api.main import create_app
from streaming_chat_api.models.entities import FlowType
from streaming_chat_api.repositories.chat import ChatRepository
from streaming_chat_api.services.replay import ReplayStreamBroker
from streaming_chat_api.services.runtime import AgentRegistry, AppResources


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / 'test.db'
    return Settings(
        app_env='test',
        app_name='streaming-chat-api-test',
        database_url=f'sqlite+aiosqlite:///{database_path}',
        redis_url='redis://unused',
        use_test_model=True,
        app_cors_origins=['http://localhost:5173'],
    )


@pytest.fixture
def llm_settings() -> Settings:
    get_settings.cache_clear()
    return Settings()


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
    engine: AsyncEngine = create_async_engine(test_settings.database.url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    http_client = httpx.AsyncClient()
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    support_client = FakeSupportClient(http_client)
    support_agent = build_support_agent(test_settings)
    replay_broker = ReplayStreamBroker(fake_redis, test_settings)

    resources = AppResources(
        settings=test_settings,
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        redis=fake_redis,
        temporal_client=None,
        support_client=support_client,
        agents=AgentRegistry(
            basic=support_agent,
            dbos=support_agent,
            temporal=support_agent,
            dbos_replay=support_agent,
        ),
        replay_broker=replay_broker,
        started_at=datetime.now(timezone.utc),
        dbos_initialized=False,
    )

    yield resources

    await fake_redis.aclose()
    await http_client.aclose()
    await engine.dispose()


@pytest.fixture(scope='session')
def postgres_dsn(docker_services) -> str:
    port = docker_services.port_for('postgres', 5432)
    return f'postgresql+asyncpg://postgres:postgres@127.0.0.1:{port}/streaming_chat_test'


@pytest.fixture
def postgres_settings(postgres_dsn: str) -> Settings:
    return Settings(
        app_env='test',
        app_name='streaming-chat-api-postgres-test',
        database_url=postgres_dsn,
        redis_url='redis://unused',
        use_test_model=True,
        app_cors_origins=['http://localhost:5173'],
    )


@pytest.fixture
async def postgres_resources(postgres_settings: Settings) -> AsyncIterator[AppResources]:
    engine: AsyncEngine = create_async_engine(postgres_settings.database.url, future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    http_client = httpx.AsyncClient()
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    support_client = FakeSupportClient(http_client)
    support_agent = build_support_agent(postgres_settings)
    replay_broker = ReplayStreamBroker(fake_redis, postgres_settings)

    resources = AppResources(
        settings=postgres_settings,
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        redis=fake_redis,
        temporal_client=None,
        support_client=support_client,
        agents=AgentRegistry(
            basic=support_agent,
            dbos=support_agent,
            temporal=support_agent,
            dbos_replay=support_agent,
        ),
        replay_broker=replay_broker,
        started_at=datetime.now(timezone.utc),
        dbos_initialized=False,
    )

    yield resources

    await fake_redis.aclose()
    await http_client.aclose()
    await engine.dispose()


@pytest.fixture
async def postgres_db_session(postgres_resources: AppResources) -> AsyncIterator[AsyncSession]:
    async with postgres_resources.session_factory() as session:
        yield session


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
async def postgres_app(postgres_resources: AppResources, postgres_settings: Settings) -> AsyncIterator[FastAPI]:
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
async def api_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
            yield client


@pytest.fixture
async def postgres_api_client(postgres_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with LifespanManager(postgres_app):
        transport = httpx.ASGITransport(app=postgres_app)
        async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
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
def agent_deps_factory(resources: AppResources):
    def factory(
        *,
        session_id: str = 'session-1',
        conversation_id: str = 'conversation-1',
        flow_type: str = FlowType.BASIC.value,
    ) -> AgentDependencies:
        return AgentDependencies(
            session_id=session_id,
            conversation_id=conversation_id,
            flow_type=flow_type,
            support_client=resources.support_client,
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


@pytest.fixture
def repository_factory():
    def factory(session: AsyncSession) -> ChatRepository:
        return ChatRepository(session)

    return factory


@pytest.fixture
def session_factory_fixture(repository_factory):
    async def factory(session: AsyncSession, *, client_id: str = 'client-1'):
        repository = repository_factory(session)
        return await repository.get_or_create_session(client_id)

    return factory


@pytest.fixture
def conversation_factory(repository_factory):
    async def factory(
        session: AsyncSession,
        *,
        session_id: UUID,
        conversation_id: UUID | None = None,
        flow_type: FlowType = FlowType.BASIC,
        title: str | None = 'Conversation',
        preview: str | None = 'Conversation',
    ):
        repository = repository_factory(session)
        return await repository.get_or_create_conversation(
            session_id=session_id,
            conversation_id=conversation_id or uuid4(),
            flow_type=flow_type,
            title=title,
            preview=preview,
        )

    return factory


@pytest.fixture
def message_factory(repository_factory):
    async def factory(
        session: AsyncSession,
        *,
        conversation_id: UUID,
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
