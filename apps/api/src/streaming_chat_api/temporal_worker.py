from __future__ import annotations

import asyncio
import logging

from temporalio.api.workflowservice.v1.request_response_pb2 import DescribeNamespaceRequest
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

from streaming_chat_api.resources import build_agents
from streaming_chat_api.settings import Settings, get_settings
from streaming_chat_api.support_client import FakeSupportClient


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


async def validate_temporal_connection(client: Client, namespace: str) -> None:
    healthy = await client.service_client.check_health()
    if not healthy:
        raise RuntimeError('Temporal service is not serving requests.')

    await client.workflow_service.describe_namespace(DescribeNamespaceRequest(namespace=namespace))


async def connect_temporal_client(settings: Settings, temporal_agent: object) -> Client:
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


async def main() -> None:
    from streaming_chat_api.temporal_workflow import SupportWorkflow

    settings = get_settings()
    agents = build_agents(settings, FakeSupportClient())

    logger.info(
        'Starting Temporal worker for task queue %s in namespace %s.',
        settings.temporal_task_queue,
        settings.temporal_namespace,
    )

    client = await connect_temporal_client(settings, agents.temporal)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[SupportWorkflow],
    )

    logger.info('Temporal worker connected to %s.', settings.temporal_target_host)
    await worker.run()


if __name__ == '__main__':
    asyncio.run(main())
