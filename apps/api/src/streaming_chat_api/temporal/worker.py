from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from streaming_chat_api.config.settings import get_settings
from streaming_chat_api.services.runtime import build_agents
from streaming_chat_api.temporal.workflows import SupportWorkflow


async def main() -> None:
    settings = get_settings()
    agents = build_agents(settings)
    SupportWorkflow.__pydantic_ai_agents__ = (agents.temporal,)

    client = await Client.connect(
        settings.temporal.target_host,
        namespace=settings.temporal.namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal.task_queue,
        workflows=[SupportWorkflow],
        plugins=[PydanticAIPlugin()],
    )
    await worker.run()


if __name__ == '__main__':
    asyncio.run(main())
