from streaming_chat_api.cli import ConversationState, _iter_sse_events, build_resume_command


def test_iter_sse_events_parses_stream_and_stops_on_done() -> None:
    lines = [
        'data: {"type":"start"}',
        '',
        'data: {"type":"text-delta","delta":"hello"}',
        '',
        'data: [DONE]',
        '',
        'data: {"type":"finish"}',
        '',
    ]

    events = list(_iter_sse_events(lines))

    assert events == [
        {'type': 'start'},
        {'type': 'text-delta', 'delta': 'hello'},
    ]


def test_build_resume_command_uses_chat_alias() -> None:
    state = ConversationState(id='conversation-123', flow='basic', messages=[])

    command = build_resume_command('http://127.0.0.1:8000', state)

    assert (
        command == 'uv run --project apps/api chat --mode basic --conversation-id conversation-123'
    )


def test_build_resume_command_includes_non_default_base_url() -> None:
    state = ConversationState(id='conversation-123', flow='temporal', messages=[])

    command = build_resume_command('http://127.0.0.1:8001', state)

    assert command == (
        'uv run --project apps/api chat --mode temporal '
        '--conversation-id conversation-123 --base-url http://127.0.0.1:8001'
    )
