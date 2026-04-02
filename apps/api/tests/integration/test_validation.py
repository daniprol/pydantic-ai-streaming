from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_chat_requires_session_header(api_client, chat_request_factory) -> None:
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={uuid4()}',
        json=chat_request_factory('hello'),
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'Missing X-Session-Id header'


@pytest.mark.asyncio
async def test_chat_requires_conversation_id(api_client, chat_request_factory) -> None:
    response = await api_client.post(
        '/api/v1/flows/basic/chat',
        json=chat_request_factory('hello'),
        headers={'X-Session-Id': 'session-1'},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_invalid_message_schema(api_client) -> None:
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={uuid4()}',
        json={'trigger': 'submit-message', 'id': 'bad', 'messages': [{'role': 'user'}]},
        headers={'X-Session-Id': 'session-1'},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_invalid_deferred_tool_results_schema(api_client, chat_request_factory) -> None:
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={uuid4()}',
        json=chat_request_factory(
            None,
            deferred_tool_results={'approvals': ['not-a-mapping']},
        ),
        headers={'X-Session-Id': 'session-1'},
    )

    assert response.status_code == 422
