from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_chat_requires_conversation_id(api_client, chat_request_factory) -> None:
    response = await api_client.post(
        '/api/v1/flows/basic/chat',
        json=chat_request_factory('hello'),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_invalid_message_schema(api_client) -> None:
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={uuid4()}',
        json={'trigger': 'submit-message', 'id': 'bad', 'messages': [{'role': 'user'}]},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_invalid_json_body(api_client) -> None:
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={uuid4()}',
        content='{"trigger": ',
        headers={'Content-Type': 'application/json'},
    )

    assert response.status_code == 422
    assert response.json()['detail'] == 'Request body must be valid JSON.'


@pytest.mark.asyncio
async def test_chat_rejects_invalid_deferred_tool_results_schema(
    api_client, chat_request_factory
) -> None:
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={uuid4()}',
        json=chat_request_factory(
            None,
            deferred_tool_results={'approvals': ['not-a-mapping']},
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_requires_existing_conversation(api_client, chat_request_factory) -> None:
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={uuid4()}',
        json=chat_request_factory('hello'),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_requires_existing_conversation(api_client) -> None:
    response = await api_client.delete(
        f'/api/v1/flows/basic/conversations/{uuid4()}',
    )

    assert response.status_code == 404
