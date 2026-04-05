from __future__ import annotations

import asyncio

from pydantic_ai_absurd import AbsurdAgent

from streaming_chat_api.database import create_engine, create_session_factory
from streaming_chat_api.resources import build_agents
from streaming_chat_api.services.absurd import ensure_absurd_queue
from streaming_chat_api.settings import get_settings
from streaming_chat_api.support_client import FakeSupportClient


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    agents = build_agents(settings, FakeSupportClient(), session_factory)
    agent = agents.absurd
    assert isinstance(agent, AbsurdAgent)
    try:
        await ensure_absurd_queue(
            agent.app,
            queue_name=settings.absurd_queue_name,
            create_if_not_exists=settings.absurd_create_queue_if_not_exists,
        )
        await agent.app.start_worker(
            worker_id=f'{settings.app_name}-absurd-worker',
            concurrency=settings.absurd_worker_concurrency,
        )
    finally:
        await agent.app.close()
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
