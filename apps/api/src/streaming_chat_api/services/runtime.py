from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import redis.asyncio as redis
from dbos import DBOS
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from temporalio.client import Client as TemporalClient

from streaming_chat_api.agents.registry import build_support_agent
from streaming_chat_api.clients.fake_support import FakeSupportClient
from streaming_chat_api.config.settings import Settings, get_settings
from streaming_chat_api.db.base import Base
from streaming_chat_api.db.session import create_engine_from_settings
from streaming_chat_api.services.replay import ReplayStreamBroker


@dataclass(slots=True)
class AgentRegistry:
    basic: object
    dbos: object
    temporal: object
    dbos_replay: object


@dataclass(slots=True)
class AppResources:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    http_client: httpx.AsyncClient
    redis: redis.Redis
    temporal_client: TemporalClient | None
    support_client: FakeSupportClient
    agents: AgentRegistry
    replay_broker: ReplayStreamBroker
    started_at: datetime
    dbos_initialized: bool


def build_agents(settings: Settings) -> AgentRegistry:
    from pydantic_ai.durable_exec.dbos import DBOSAgent
    from pydantic_ai.durable_exec.temporal import TemporalAgent

    support_agent = build_support_agent(settings)
    return AgentRegistry(
        basic=support_agent,
        dbos=DBOSAgent(support_agent, name='support-assistant-dbos'),
        temporal=TemporalAgent(support_agent, name='support-assistant-temporal'),
        dbos_replay=DBOSAgent(support_agent, name='support-assistant-dbos-replay'),
    )


async def create_resources(settings: Settings | None = None) -> AppResources:
    settings = settings or get_settings()
    engine = create_engine_from_settings(settings)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    http_client = httpx.AsyncClient(timeout=30.0)
    redis_client = redis.from_url(settings.redis.url, decode_responses=True)
    support_client = FakeSupportClient(http_client)
    agents = build_agents(settings)

    temporal_client: TemporalClient | None = None
    try:
        temporal_client = await TemporalClient.connect(
            settings.temporal.target_host,
            namespace=settings.temporal.namespace,
        )
    except Exception:
        temporal_client = None

    dbos_initialized = False
    try:
        DBOS(config={'name': settings.app.name, 'system_database_url': settings.dbos.system_database_url})
        DBOS.launch()
        dbos_initialized = True
    except Exception:
        dbos_initialized = False

    if settings.database.url.startswith('sqlite'):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    replay_broker = ReplayStreamBroker(redis_client, settings)

    return AppResources(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        redis=redis_client,
        temporal_client=temporal_client,
        support_client=support_client,
        agents=agents,
        replay_broker=replay_broker,
        started_at=datetime.now(timezone.utc),
        dbos_initialized=dbos_initialized,
    )


async def close_resources(resources: AppResources) -> None:
    await resources.http_client.aclose()
    await resources.redis.aclose()
    await resources.engine.dispose()


def build_lifespan(settings: Settings | None = None):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resources = await create_resources(settings)
        app.state.resources = resources
        app.state.settings = resources.settings
        try:
            yield
        finally:
            await close_resources(resources)

    return lifespan


lifespan = build_lifespan()


async def check_postgres(resources: AppResources) -> tuple[bool, str]:
    try:
        async with resources.session_factory() as session:
            await session.execute(text('select 1'))
        return True, 'ok'
    except Exception as exc:
        return False, str(exc)


async def check_redis(resources: AppResources) -> tuple[bool, str]:
    try:
        await resources.redis.ping()
        return True, 'ok'
    except Exception as exc:
        return False, str(exc)


async def check_temporal(resources: AppResources) -> tuple[bool, str]:
    if resources.temporal_client is None:
        return False, 'client unavailable'
    try:
        await resources.temporal_client.list_namespaces()
        return True, 'ok'
    except Exception as exc:
        return False, str(exc)
