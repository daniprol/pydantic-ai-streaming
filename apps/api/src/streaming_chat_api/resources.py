from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import redis.asyncio as redis
from dbos import DBOS
from absurd_sdk import AsyncAbsurd
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from temporalio.client import Client as TemporalClient

from pydantic_ai_absurd import AbsurdAgent

from streaming_chat_api.agents import build_support_agent
from streaming_chat_api.database import create_engine, create_session_factory
from streaming_chat_api.replay import ReplayStreamBroker
from streaming_chat_api.settings import Settings, get_settings
from streaming_chat_api.support_client import FakeSupportClient


@dataclass(slots=True)
class ChatAgents:
    basic: object
    absurd: object
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
    agents: ChatAgents
    replay_broker: ReplayStreamBroker
    started_at: datetime
    dbos_initialized: bool


def build_agents(settings: Settings, support_client: FakeSupportClient) -> ChatAgents:
    from pydantic_ai.durable_exec.dbos import DBOSAgent
    from pydantic_ai.durable_exec.temporal import TemporalAgent
    from streaming_chat_api.services.common import stream_callback_events, stream_dbos_events

    support_agent = build_support_agent(settings, support_client)
    absurd_queue_name = f'{settings.app_name}-absurd'
    absurd_app = AsyncAbsurd(settings.dbos_system_database_url, queue_name=absurd_queue_name)
    return ChatAgents(
        basic=support_agent,
        absurd=AbsurdAgent(
            absurd_app,
            support_agent,
            name='support-assistant-absurd',
            event_stream_handler=stream_callback_events,
        ),
        dbos=DBOSAgent(
            support_agent,
            name='support-assistant-dbos',
            event_stream_handler=stream_dbos_events,
        ),
        temporal=TemporalAgent(support_agent, name='support-assistant-temporal'),
        dbos_replay=DBOSAgent(
            support_agent,
            name='support-assistant-dbos-replay',
            event_stream_handler=stream_dbos_events,
        ),
    )


async def create_resources(settings: Settings | None = None) -> AppResources:
    resolved_settings = settings or get_settings()
    engine = create_engine(resolved_settings)
    session_factory = create_session_factory(engine)
    http_client = httpx.AsyncClient(timeout=30.0)
    redis_client = redis.from_url(resolved_settings.redis_url, decode_responses=True)
    support_client = FakeSupportClient()
    agents = build_agents(resolved_settings, support_client)

    temporal_client: TemporalClient | None = None
    try:
        temporal_client = await TemporalClient.connect(
            resolved_settings.temporal_target_host,
            namespace=resolved_settings.temporal_namespace,
        )
    except Exception:
        temporal_client = None

    dbos_initialized = False
    try:
        DBOS(
            config={
                'name': resolved_settings.app_name,
                'system_database_url': resolved_settings.dbos_system_database_url,
            }
        )
        DBOS.launch()
        dbos_initialized = True
    except Exception:
        dbos_initialized = False

    return AppResources(
        settings=resolved_settings,
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        redis=redis_client,
        temporal_client=temporal_client,
        support_client=support_client,
        agents=agents,
        replay_broker=ReplayStreamBroker(redis_client, resolved_settings),
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
