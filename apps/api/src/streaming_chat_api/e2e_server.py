from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4
from uuid import UUID

import fakeredis.aioredis
import uvicorn
from fastapi import FastAPI
from pydantic_ai.tools import DeferredToolResults

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
from streaming_chat_api.settings import Settings
from streaming_chat_api.support_client import FakeSupportClient


class _NoopAsyncClient:
    async def aclose(self) -> None:
        return None


class _LocalTemporalClient:
    def __init__(self, resources: AppResources):
        self.resources = resources

    async def list_namespaces(self) -> None:
        raise RuntimeError('Temporal server is not running for e2e helper app.')

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


def build_e2e_settings() -> Settings:
    database_path = Path(gettempdir()) / f'streaming-chat-e2e-{uuid4()}.sqlite3'
    if database_path.exists():
        database_path.unlink()

    return Settings(
        app_env='test',
        app_name='streaming-chat-api-e2e',
        app_cors_origins=['http://127.0.0.1:5173'],
        database_url=f'sqlite+aiosqlite:///{database_path}',
        redis_url='redis://unused',
        use_test_model=True,
    )


def build_e2e_app() -> FastAPI:
    settings = build_e2e_settings()
    app = create_app(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        http_client = _NoopAsyncClient()
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
        resources.temporal_client = _LocalTemporalClient(resources)

        app.state.resources = resources
        app.state.settings = settings

        try:
            yield
        finally:
            await fake_redis.aclose()
            await http_client.aclose()
            await engine.dispose()

    app.router.lifespan_context = lifespan
    return app


app = build_e2e_app()


def main() -> None:
    uvicorn.run(app, host='127.0.0.1', port=8001, log_level='warning')


if __name__ == '__main__':
    main()
