
import pytest


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
