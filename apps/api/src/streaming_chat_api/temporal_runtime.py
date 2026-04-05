from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pydantic_ai.durable_exec.temporal import TemporalAgent

from streaming_chat_api.agents import build_support_agent
from streaming_chat_api.database import create_engine, create_session_factory
from streaming_chat_api.replay import ReplayStreamBroker
from streaming_chat_api.settings import Settings, get_settings
from streaming_chat_api.support_client import FakeSupportClient


@dataclass(slots=True)
class TemporalWorkerRuntime:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: redis.Redis
    replay_broker: ReplayStreamBroker


_runtime: TemporalWorkerRuntime | None = None
_temporal_agent: TemporalAgent | None = None


def build_temporal_agent(settings: Settings) -> TemporalAgent:
    from streaming_chat_api.temporal_streaming import stream_temporal_events

    support_agent = build_support_agent(settings, FakeSupportClient())
    return TemporalAgent(
        support_agent,
        name='support-assistant-temporal',
        event_stream_handler=stream_temporal_events,
    )


def configure_temporal_agent(settings: Settings) -> TemporalAgent:
    global _temporal_agent
    _temporal_agent = build_temporal_agent(settings)
    return _temporal_agent


def get_temporal_agent(settings: Settings | None = None) -> TemporalAgent:
    global _temporal_agent
    if settings is not None:
        return configure_temporal_agent(settings)
    if _temporal_agent is None:
        _temporal_agent = build_temporal_agent(get_settings())
    return _temporal_agent


async def create_temporal_worker_runtime(settings: Settings | None = None) -> TemporalWorkerRuntime:
    global _runtime

    resolved_settings = settings or get_settings()
    configure_temporal_agent(resolved_settings)

    engine = create_engine(resolved_settings)
    session_factory = create_session_factory(engine)
    redis_client = redis.from_url(resolved_settings.redis_url, decode_responses=True)
    runtime = TemporalWorkerRuntime(
        settings=resolved_settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis_client,
        replay_broker=ReplayStreamBroker(redis_client, resolved_settings),
    )
    _runtime = runtime
    return runtime


def get_temporal_worker_runtime() -> TemporalWorkerRuntime:
    if _runtime is None:  # pragma: no cover - worker initialization must happen first
        raise RuntimeError('Temporal worker runtime is not initialized.')
    return _runtime


async def close_temporal_worker_runtime(runtime: TemporalWorkerRuntime) -> None:
    global _runtime

    await runtime.redis.aclose()
    await runtime.engine.dispose()
    if _runtime is runtime:
        _runtime = None
