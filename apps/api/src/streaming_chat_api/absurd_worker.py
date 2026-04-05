from __future__ import annotations

import asyncio

from pydantic_ai_absurd import AbsurdAgent

from streaming_chat_api.resources import build_agents
from streaming_chat_api.settings import get_settings
from streaming_chat_api.support_client import FakeSupportClient


async def main() -> None:
    settings = get_settings()
    agents = build_agents(settings, FakeSupportClient())
    agent = agents.absurd
    assert isinstance(agent, AbsurdAgent)
    await agent.app.start_worker(worker_id=f'{settings.app_name}-absurd-worker')


if __name__ == '__main__':
    asyncio.run(main())
