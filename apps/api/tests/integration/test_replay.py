import pytest


def first_stream_event_id(body: str) -> str:
    for line in body.splitlines():
        if line.startswith('id: '):
            return line[4:]
    raise AssertionError('Expected stream to contain an SSE event id')


@pytest.mark.asyncio
async def test_replay_broker_replays_chunks_in_order(resources) -> None:
    replay_id = 'replay-1'
    await resources.replay_broker.append_chunk(replay_id, 'data: first\n\n')
    second_id = await resources.replay_broker.append_chunk(replay_id, 'data: second\n\n')
    await resources.replay_broker.append_complete(replay_id)

    chunks: list[str] = []
    async for chunk in resources.replay_broker.replay_stream(replay_id, None):
        chunks.append(chunk)

    assert chunks[0].endswith('data: first\n\n')
    assert chunks[1].startswith(f'id: {second_id}\n')
    assert chunks[1].endswith('data: second\n\n')


@pytest.mark.asyncio
async def test_replay_broker_emits_error_event_when_stream_fails(resources) -> None:
    replay_id = 'replay-error'

    async def failing_stream():
        yield 'data: first\n\n'
        raise RuntimeError('boom')

    resources.replay_broker.start_stream(replay_id, failing_stream())

    chunks: list[str] = []
    async for chunk in resources.replay_broker.replay_stream(replay_id, None):
        chunks.append(chunk)

    assert any('data: first' in chunk for chunk in chunks)
    assert any('"type": "error"' in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_replay_broker_replays_from_last_event_id(resources) -> None:
    replay_id = 'replay-2'
    first_id = await resources.replay_broker.append_chunk(replay_id, 'data: first\n\n')
    await resources.replay_broker.append_chunk(replay_id, 'data: second\n\n')
    await resources.replay_broker.append_complete(replay_id)

    chunks: list[str] = []
    async for chunk in resources.replay_broker.replay_stream(replay_id, first_id):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].endswith('data: second\n\n')


@pytest.mark.asyncio
async def test_replay_endpoint_resumes_after_last_event_id(api_client, resources) -> None:
    replay_id = 'replay-http'
    first_id = await resources.replay_broker.append_chunk(replay_id, 'data: first\n\n')
    await resources.replay_broker.append_chunk(replay_id, 'data: second\n\n')
    await resources.replay_broker.append_complete(replay_id)

    async with api_client.stream(
        'GET',
        f'/api/v1/flows/dbos-replay/streams/{replay_id}/replay?last_event_id={first_id}',
    ) as response:
        chunks = [chunk async for chunk in response.aiter_text()]

    body = ''.join(chunks)

    assert response.status_code == 200
    assert 'data: second' in body
    assert 'data: first' not in body


@pytest.mark.asyncio
async def test_temporal_replay_endpoint_resumes_after_last_event_id(api_client, resources) -> None:
    replay_id = 'temporal-http'
    first_id = await resources.replay_broker.append_chunk(replay_id, 'data: first\n\n')
    await resources.replay_broker.append_chunk(replay_id, 'data: second\n\n')
    await resources.replay_broker.append_complete(replay_id)

    async with api_client.stream(
        'GET',
        f'/api/v1/flows/temporal/streams/{replay_id}/replay?last_event_id={first_id}',
    ) as response:
        chunks = [chunk async for chunk in response.aiter_text()]

    body = ''.join(chunks)

    assert response.status_code == 200
    assert 'data: second' in body
    assert 'data: first' not in body


async def read_first_sse_event_id(response) -> str:
    event_id: str | None = None
    async for line in response.aiter_lines():
        if line.startswith('id: '):
            event_id = line[4:]
        if event_id is not None and line == '':
            return event_id
    raise AssertionError('Expected at least one SSE event id')


@pytest.mark.asyncio
@pytest.mark.parametrize('flow', ['dbos-replay', 'temporal'])
async def test_replayable_flow_continues_after_client_disconnect(
    api_client,
    chat_request_factory,
    flow: str,
) -> None:
    create_response = await api_client.post(f'/api/v1/flows/{flow}/conversations')
    conversation_id = create_response.json()['conversation']['id']

    async with api_client.stream(
        'POST',
        f'/api/v1/flows/{flow}/chat?conversation_id={conversation_id}',
        json=chat_request_factory(f'Replay this {flow} answer'),
    ) as response:
        assert response.status_code == 200
        first_id = await read_first_sse_event_id(response)

    replay = await api_client.get(
        f'/api/v1/flows/{flow}/streams/{conversation_id}/replay?last_event_id={first_id}',
        timeout=5,
    )
    messages = await api_client.get(
        f'/api/v1/flows/{flow}/conversations/{conversation_id}/messages'
    )

    assert replay.status_code == 200
    assert f'id: {first_id}' not in replay.text
    assert ('{"type":"text-delta"' in replay.text) or ('{"type":"finish"' in replay.text)
    assert messages.status_code == 200
    assert any(message['role'] == 'assistant' for message in messages.json()['messages'])


@pytest.mark.asyncio
async def test_dbos_replay_flow_clears_active_replay_id_after_completion(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/dbos-replay/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/dbos-replay/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Replay this answer'),
    )
    messages = await api_client.get(
        f'/api/v1/flows/dbos-replay/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert messages.status_code == 200
    assert messages.json()['active_replay_id'] is None


@pytest.mark.asyncio
async def test_dbos_replay_flow_exposes_replay_header(api_client, chat_request_factory) -> None:
    create_response = await api_client.post('/api/v1/flows/dbos-replay/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/dbos-replay/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Replay this answer'),
    )

    assert response.status_code == 200
    assert response.headers['x-replay-id'] == conversation_id
    assert first_stream_event_id(response.text)


@pytest.mark.asyncio
async def test_temporal_flow_exposes_replay_header_and_clears_active_replay_id(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/temporal/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/temporal/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Replay this temporal answer'),
    )
    messages = await api_client.get(
        f'/api/v1/flows/temporal/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert response.headers['x-replay-id'] == conversation_id
    assert first_stream_event_id(response.text)
    assert messages.status_code == 200
    assert messages.json()['active_replay_id'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('flow', ['dbos-replay', 'temporal'])
async def test_replayable_flows_use_a_new_replay_id_per_turn(
    api_client,
    chat_request_factory,
    flow: str,
) -> None:
    create_response = await api_client.post(f'/api/v1/flows/{flow}/conversations')
    conversation_id = create_response.json()['conversation']['id']

    first_response = await api_client.post(
        f'/api/v1/flows/{flow}/chat?conversation_id={conversation_id}',
        json=chat_request_factory('hello'),
    )
    second_response = await api_client.post(
        f'/api/v1/flows/{flow}/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'Where is my order?', request_id='request-2', message_id='message-2'
        ),
    )
    messages = await api_client.get(
        f'/api/v1/flows/{flow}/conversations/{conversation_id}/messages'
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.headers['x-replay-id'] != second_response.headers['x-replay-id']
    assert second_response.text != first_response.text
    assert 'https://example.com/help/streaming-delays' in second_response.text
    assert messages.status_code == 200
    assert len(messages.json()['messages']) >= 4
