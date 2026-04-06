from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack

from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from pydantic_ai.durable_exec.temporal import AgentPlugin, PydanticAIPlugin

from streaming_chat_api.settings import Settings, get_settings
from streaming_chat_api.temporal_activities import (
    clear_temporal_replay,
    fail_temporal_replay_stream,
    finish_temporal_replay_stream,
    persist_temporal_run_output,
)
from streaming_chat_api.temporal_health import validate_temporal_connection
from streaming_chat_api.temporal_runtime import (
    close_temporal_worker_runtime,
    create_temporal_worker_runtime,
    get_temporal_agent,
)
from streaming_chat_api.temporal_workflow import SupportWorkflow


logger = logging.getLogger(__name__)

RETRYABLE_TEMPORAL_RPC_STATUSES = frozenset(
    {
        RPCStatusCode.DEADLINE_EXCEEDED,
        RPCStatusCode.INTERNAL,
        RPCStatusCode.UNKNOWN,
        RPCStatusCode.UNAVAILABLE,
    }
)


def is_retryable_temporal_connection_error(error: BaseException) -> bool:
    if isinstance(error, RPCError):
        return error.status in RETRYABLE_TEMPORAL_RPC_STATUSES

    return isinstance(error, OSError | ConnectionError | TimeoutError)


async def connect_temporal_client(settings: Settings) -> Client:
    temporal_agent = get_temporal_agent()
    plugins = [PydanticAIPlugin(), AgentPlugin(temporal_agent)]

    def log_retry(retry_state: RetryCallState) -> None:
        error = retry_state.outcome.exception()
        logger.warning(
            'Temporal unavailable at %s for namespace %s (attempt %s/%s): %s. Retrying in %.1fs.',
            settings.temporal_target_host,
            settings.temporal_namespace,
            retry_state.attempt_number,
            settings.temporal_connect_attempts,
            error,
            retry_state.next_action.sleep,
        )

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(settings.temporal_connect_attempts),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception(is_retryable_temporal_connection_error),
        before_sleep=log_retry,
        reraise=True,
    ):
        with attempt:
            client = await Client.connect(
                settings.temporal_target_host,
                namespace=settings.temporal_namespace,
                plugins=plugins,
            )
            await validate_temporal_connection(client, settings.temporal_namespace)
            return client

    raise RuntimeError('Temporal client connection retry loop exited unexpectedly.')


async def check_temporal_worker_health(settings: Settings | None = None) -> None:
    resolved_settings = settings or get_settings()
    # Build the agent/runtime-side config eagerly so import/config issues fail fast.
    get_temporal_agent(resolved_settings)
    client = await Client.connect(
        resolved_settings.temporal_target_host,
        namespace=resolved_settings.temporal_namespace,
    )
    await validate_temporal_connection(client, resolved_settings.temporal_namespace)


async def main() -> None:
    settings = get_settings()
    runtime = await create_temporal_worker_runtime(settings)

    logger.info(
        'Starting Temporal worker for task queue %s in namespace %s.',
        settings.temporal_task_queue,
        settings.temporal_namespace,
    )

    client = await connect_temporal_client(settings)
    async with AsyncExitStack() as stack:
        stack.push_async_callback(close_temporal_worker_runtime, runtime)
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[SupportWorkflow],
            activities=[
                persist_temporal_run_output,
                clear_temporal_replay,
                finish_temporal_replay_stream,
                fail_temporal_replay_stream,
            ],
        )

        logger.info('Temporal worker connected to %s.', settings.temporal_target_host)
        await worker.run()


if __name__ == '__main__':
    asyncio.run(main())
