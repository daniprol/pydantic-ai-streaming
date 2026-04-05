import pytest


async def read_first_sse_event_id(response) -> str:
    event_id: str | None = None
    async for line in response.aiter_lines():
        if line.startswith('id: '):
            event_id = line[4:]
        if event_id is not None and line == '':
            return event_id
    raise AssertionError('Expected at least one SSE event id')


@pytest.mark.llm
@pytest.mark.asyncio
async def test_basic_flow_streams_with_real_llm(real_api_client, chat_request_factory) -> None:
    create_response = await real_api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await real_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'Reply with a short plain-text acknowledgement and do not call any tools.'
        ),
    )
    messages = await real_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert response.headers['content-type'].startswith('text/event-stream')
    assert '{"type":"text-delta"' in response.text
    assert 'data: [DONE]' in response.text

    assistant_messages = [
        message for message in messages.json()['messages'] if message['role'] == 'assistant'
    ]
    assistant_text_parts = [
        part['text']
        for message in assistant_messages
        for part in message['parts']
        if part['type'] == 'text'
    ]

    assert assistant_messages
    assert any(text.strip() for text in assistant_text_parts)


@pytest.mark.llm
@pytest.mark.asyncio
@pytest.mark.parametrize('flow', ['dbos-replay', 'temporal'])
async def test_replayable_flow_streams_with_real_llm_and_supports_replay(
    real_api_client,
    chat_request_factory,
    flow: str,
) -> None:
    create_response = await real_api_client.post(f'/api/v1/flows/{flow}/conversations')
    conversation_id = create_response.json()['conversation']['id']

    async with real_api_client.stream(
        'POST',
        f'/api/v1/flows/{flow}/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'Reply with a short plain-text acknowledgement and do not call any tools.'
        ),
    ) as response:
        replay_id = response.headers['x-replay-id']
        first_event_id = await read_first_sse_event_id(response)

    replay = await real_api_client.get(
        f'/api/v1/flows/{flow}/streams/{replay_id}/replay?last_event_id={first_event_id}',
        timeout=10,
    )
    messages = await real_api_client.get(
        f'/api/v1/flows/{flow}/conversations/{conversation_id}/messages'
    )

    assert replay.status_code == 200
    assert replay.headers['content-type'].startswith('text/event-stream')
    assert f'id: {first_event_id}' not in replay.text
    assistant_messages = [
        message for message in messages.json()['messages'] if message['role'] == 'assistant'
    ]
    assistant_text_parts = [
        part['text']
        for message in assistant_messages
        for part in message['parts']
        if part['type'] == 'text'
    ]

    assert assistant_messages
    assert any(text.strip() for text in assistant_text_parts)


@pytest.mark.llm
@pytest.mark.asyncio
@pytest.mark.parametrize('flow', ['dbos-replay', 'temporal'])
async def test_replayable_flow_uses_distinct_replay_ids_across_turns_with_real_llm(
    real_api_client,
    chat_request_factory,
    flow: str,
) -> None:
    create_response = await real_api_client.post(f'/api/v1/flows/{flow}/conversations')
    conversation_id = create_response.json()['conversation']['id']

    first_response = await real_api_client.post(
        f'/api/v1/flows/{flow}/chat?conversation_id={conversation_id}',
        json=chat_request_factory('hello'),
    )
    second_response = await real_api_client.post(
        f'/api/v1/flows/{flow}/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'Where is my order?', request_id='request-2', message_id='message-2'
        ),
    )
    messages = await real_api_client.get(
        f'/api/v1/flows/{flow}/conversations/{conversation_id}/messages'
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.headers['x-replay-id'] != second_response.headers['x-replay-id']
    assert second_response.text != first_response.text
    assert messages.status_code == 200
    assistant_messages = [
        message for message in messages.json()['messages'] if message['role'] == 'assistant'
    ]

    assert len(assistant_messages) >= 2
