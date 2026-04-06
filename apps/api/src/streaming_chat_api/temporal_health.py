from __future__ import annotations

from temporalio.api.workflowservice.v1.request_response_pb2 import DescribeNamespaceRequest
from temporalio.client import Client


async def validate_temporal_connection(client: Client, namespace: str) -> None:
    healthy = await client.service_client.check_health()
    if not healthy:
        raise RuntimeError('Temporal service is not serving requests.')

    await client.workflow_service.describe_namespace(DescribeNamespaceRequest(namespace=namespace))
