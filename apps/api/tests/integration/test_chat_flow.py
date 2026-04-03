import pytest


@pytest.mark.asyncio
async def test_basic_flow_creates_and_lists_conversation(api_client, chat_request_factory) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Where is my order?'),
    )
    conversations = await api_client.get('/api/v1/flows/basic/conversations')
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert conversations.status_code == 200
    assert conversations.json()['total'] == 1
    assert conversations.json()['items'][0]['id'] == str(conversation_id)
    assert messages.status_code == 200
    assert messages.json()['conversation_id'] == str(conversation_id)
    assert len(messages.json()['messages']) >= 1


@pytest.mark.asyncio
async def test_chat_accepts_deferred_tool_results_without_new_user_message(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Check the policy'),
    )
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-2',
            deferred_tool_results={'approvals': {'approval-1': True}},
        ),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_replay_flow_exposes_replay_endpoint(api_client, chat_request_factory) -> None:
    create_response = await api_client.post('/api/v1/flows/dbos-replay/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/dbos-replay/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Stream this answer'),
    )
    replay = await api_client.get(
        f'/api/v1/flows/dbos-replay/streams/{conversation_id}/replay',
        timeout=2,
    )

    assert replay.status_code == 200
    assert replay.headers['content-type'].startswith('text/event-stream')


@pytest.mark.asyncio
async def test_missing_conversation_returns_404(api_client) -> None:
    response = await api_client.get(
        '/api/v1/flows/basic/conversations/87319ab1-c3d1-4e7b-a238-5b932aef2e9a/messages'
    )

    assert response.status_code == 404
