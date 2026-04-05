from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.service import RPCError, RPCStatusCode

from streaming_chat_api.temporal_worker import (
    is_retryable_temporal_connection_error,
    validate_temporal_connection,
)


@pytest.mark.parametrize(
    'status',
    [
        RPCStatusCode.DEADLINE_EXCEEDED,
        RPCStatusCode.INTERNAL,
        RPCStatusCode.UNKNOWN,
        RPCStatusCode.UNAVAILABLE,
    ],
)
def test_retryable_temporal_connection_error_for_transient_rpc_statuses(
    status: RPCStatusCode,
) -> None:
    assert is_retryable_temporal_connection_error(RPCError('boom', status, b'')) is True


@pytest.mark.parametrize(
    'status',
    [
        RPCStatusCode.INVALID_ARGUMENT,
        RPCStatusCode.NOT_FOUND,
        RPCStatusCode.PERMISSION_DENIED,
        RPCStatusCode.UNAUTHENTICATED,
    ],
)
def test_retryable_temporal_connection_error_rejects_non_transient_rpc_statuses(
    status: RPCStatusCode,
) -> None:
    assert is_retryable_temporal_connection_error(RPCError('boom', status, b'')) is False


@pytest.mark.asyncio
async def test_validate_temporal_connection_checks_health_and_namespace() -> None:
    client = Mock()
    client.service_client = Mock(check_health=AsyncMock(return_value=True))
    client.workflow_service = Mock(describe_namespace=AsyncMock())

    await validate_temporal_connection(client, 'default')

    client.service_client.check_health.assert_awaited_once_with()
    client.workflow_service.describe_namespace.assert_awaited_once()
    request = client.workflow_service.describe_namespace.await_args.args[0]
    assert request.namespace == 'default'


@pytest.mark.asyncio
async def test_validate_temporal_connection_fails_when_service_is_not_serving() -> None:
    client = Mock()
    client.service_client = Mock(check_health=AsyncMock(return_value=False))
    client.workflow_service = Mock(describe_namespace=AsyncMock())

    with pytest.raises(RuntimeError, match='not serving'):
        await validate_temporal_connection(client, 'default')

    client.workflow_service.describe_namespace.assert_not_awaited()
