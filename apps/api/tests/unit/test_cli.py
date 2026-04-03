import httpx

from streaming_chat_api.cli import ConversationState, _iter_sse_events, build_resume_command
from streaming_chat_api.cli import format_http_error


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


def test_format_http_error_prefers_json_detail() -> None:
    request = httpx.Request('GET', 'http://example.com/api')
    response = httpx.Response(500, request=request, json={'detail': 'boom'})
    error = httpx.HTTPStatusError('server error', request=request, response=response)

    assert format_http_error(error) == 'HTTP 500: boom'
