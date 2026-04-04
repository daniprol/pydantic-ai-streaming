from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from streaming_chat_api.resources import build_agents
from streaming_chat_api.settings import get_settings
from streaming_chat_api.support_client import FakeSupportClient
from streaming_chat_api.temporal_workflow import SupportWorkflow


logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    agents = build_agents(settings, FakeSupportClient())
    SupportWorkflow.__pydantic_ai_agents__ = (agents.temporal,)

    for attempt in range(1, 31):
        try:
            client = await Client.connect(
                settings.temporal_target_host,
                namespace=settings.temporal_namespace,
            )
            break
        except Exception:
            if attempt == 30:
                raise
            logger.warning(
                'Temporal unavailable at %s, retrying (%s/30)',
                settings.temporal_target_host,
                attempt,
            )
            await asyncio.sleep(1)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[SupportWorkflow],
        plugins=[PydanticAIPlugin()],
    )
    await worker.run()


if __name__ == '__main__':
    asyncio.run(main())
