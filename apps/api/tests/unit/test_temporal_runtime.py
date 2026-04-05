from types import SimpleNamespace

import pytest
from pydantic_ai.messages import PartEndEvent, PartStartEvent, TextPart

import streaming_chat_api.temporal_runtime as temporal_runtime
from streaming_chat_api.agents import AgentDependencies, build_support_agent
from streaming_chat_api.models import FlowType
from streaming_chat_api.repository import ConversationRepository
from streaming_chat_api.services.common import serialize_model_messages
from streaming_chat_api.support_client import FakeSupportClient
from streaming_chat_api.temporal_activities import (
    PersistRunOutputInput,
    persist_temporal_run_output,
)
from streaming_chat_api.temporal_runtime import TemporalWorkerRuntime
from streaming_chat_api.temporal_streaming import (
    _publisher_locks,
    _publisher_states,
    finish_temporal_stream,
    publish_temporal_event,
)


class _RecordingReplayBroker:
    def __init__(self) -> None:
        self.chunks: list[tuple[str, str]] = []
        self.completed: list[str] = []

    async def append_chunk(self, replay_id: str, chunk: str) -> str:
        self.chunks.append((replay_id, chunk))
        return f'{len(self.chunks)}-0'

    async def append_complete(self, replay_id: str) -> None:
        self.completed.append(replay_id)


@pytest.mark.asyncio
async def test_temporal_streaming_publishes_chunks_and_completion(monkeypatch) -> None:
    broker = _RecordingReplayBroker()
    runtime = SimpleNamespace(replay_broker=broker)
    monkeypatch.setattr('streaming_chat_api.temporal_runtime._runtime', runtime)
    _publisher_locks.clear()
    _publisher_states.clear()

    await publish_temporal_event(
        replay_id='replay-1',
        request_body='{"trigger":"submit-message","id":"request-1","messages":[{"id":"message-1","role":"user","parts":[{"type":"text","text":"hi"}]}]}',
        accept='text/event-stream',
        event=PartStartEvent(index=0, part=TextPart(content='hello')),
    )
    await publish_temporal_event(
        replay_id='replay-1',
        request_body='{"trigger":"submit-message","id":"request-1","messages":[{"id":"message-1","role":"user","parts":[{"type":"text","text":"hi"}]}]}',
        accept='text/event-stream',
        event=PartEndEvent(index=0, part=TextPart(content='hello')),
    )
    await finish_temporal_stream(
        replay_id='replay-1',
        request_body='{"trigger":"submit-message","id":"request-1","messages":[{"id":"message-1","role":"user","parts":[{"type":"text","text":"hi"}]}]}',
        accept='text/event-stream',
    )

    encoded_stream = ''.join(chunk for _, chunk in broker.chunks)
    assert '"type":"text-delta"' in encoded_stream
    assert 'data: [DONE]' in encoded_stream
    assert broker.completed == ['replay-1']


@pytest.mark.asyncio
async def test_persist_temporal_run_output_activity_stores_messages_and_clears_replay(
    resources,
    test_settings,
    conversation_factory,
) -> None:
    async with resources.session_factory() as session:
        conversation = await conversation_factory(
            session,
            flow_type=FlowType.TEMPORAL,
            active_replay_id='replay-1',
        )
        await session.commit()
    agent = build_support_agent(test_settings, FakeSupportClient())
    result = await agent.run('hello', deps=AgentDependencies(conversation_id=str(conversation.id)))

    runtime = TemporalWorkerRuntime(
        settings=resources.settings,
        engine=resources.engine,
        session_factory=resources.session_factory,
        redis=resources.redis,
        replay_broker=resources.replay_broker,
    )

    try:
        temporal_runtime._runtime = runtime
        await persist_temporal_run_output(
            PersistRunOutputInput(
                conversation_id=str(conversation.id),
                new_messages=serialize_model_messages(result.new_messages()),
            )
        )
    finally:
        temporal_runtime._runtime = None

    async with resources.session_factory() as session:
        repository = ConversationRepository(session)
        stored_messages = await repository.list_messages(conversation.id)
        stored_conversation = await repository.get_conversation(conversation.id, FlowType.TEMPORAL)

    assert len(stored_messages) >= 1
    assert stored_conversation is not None
    assert stored_conversation.active_replay_id is None
