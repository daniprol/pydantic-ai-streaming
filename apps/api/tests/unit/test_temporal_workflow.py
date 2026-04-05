from streaming_chat_api.temporal_workflow import (
    build_temporal_workflow_id,
    build_temporal_workflow_input,
)


def test_build_temporal_workflow_id_uses_conversation_and_replay_ids() -> None:
    workflow_id = build_temporal_workflow_id('conversation-123', 'replay-456')

    assert workflow_id == 'temporal-chat-conversation-123-replay-456'


def test_build_temporal_workflow_input_preserves_request_context() -> None:
    payload = build_temporal_workflow_input(
        conversation_id='conversation-123',
        replay_id='replay-456',
        request_body=b'{"trigger":"submit-message"}',
        accept='text/event-stream',
        message_history=[{'kind': 'history'}],
        deferred_tool_results={'approvals': {'approval-1': True}, 'calls': {}},
    )

    assert payload.conversation_id == 'conversation-123'
    assert payload.replay_id == 'replay-456'
    assert payload.request_body == '{"trigger":"submit-message"}'
    assert payload.accept == 'text/event-stream'
    assert payload.message_history == [{'kind': 'history'}]
    assert payload.deferred_tool_results == {'approvals': {'approval-1': True}, 'calls': {}}
