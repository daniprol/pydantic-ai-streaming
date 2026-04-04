from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import gettempdir

import fakeredis.aioredis
import httpx
import uvicorn
from fastapi import FastAPI

from streaming_chat_api.agents import build_support_agent
from streaming_chat_api.database import Base, create_engine, create_session_factory
from streaming_chat_api.main import create_app
from streaming_chat_api.replay import ReplayStreamBroker
from streaming_chat_api.resources import AppResources, ChatAgents
from streaming_chat_api.settings import Settings
from streaming_chat_api.support_client import FakeSupportClient


def build_e2e_settings() -> Settings:
    database_path = Path(gettempdir()) / 'streaming-chat-e2e.sqlite3'
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
                temporal=support_agent,
                dbos_replay=support_agent,
            ),
            replay_broker=ReplayStreamBroker(fake_redis, settings),
            started_at=datetime.now(timezone.utc),
            dbos_initialized=False,
        )

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
