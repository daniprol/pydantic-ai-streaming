from io import StringIO

import httpx
import pytest
from rich.console import Console

from streaming_chat_api.cli import (
    ConversationState,
    SSEFrame,
    StreamOptions,
    _iter_sse_frames,
    build_resume_command,
    format_http_error,
    stream_chat_events,
)


class FakeStream:
    def __init__(self, replay_id: str | None, items):
        self.replay_id = replay_id
        self._items = iter(items)
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        item = next(self._items)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self, initial_stream: FakeStream, replay_streams: list[FakeStream]):
        self.initial_stream = initial_stream
        self.replay_streams = list(replay_streams)
        self.replay_calls: list[tuple[str, str | None]] = []

    def open_chat_stream(self, flow, conversation_id, messages):
        return self.initial_stream

    def open_replay_stream(self, flow, replay_id, last_event_id):
        self.replay_calls.append((replay_id, last_event_id))
        return self.replay_streams.pop(0)


def test_iter_sse_frames_parses_event_ids_and_stops_on_done() -> None:
    lines = [
        'id: 1-0',
        'data: {"type":"start"}',
        '',
        'id: 1-1',
        'data: {"type":"text-delta","delta":"hello"}',
        '',
        'data: [DONE]',
        '',
        'data: {"type":"finish"}',
        '',
    ]

    events = list(_iter_sse_frames(lines))

    assert events == [
        SSEFrame(event_id='1-0', payload={'type': 'start'}),
        SSEFrame(event_id='1-1', payload={'type': 'text-delta', 'delta': 'hello'}),
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


def test_build_resume_command_includes_resume_stream_flag() -> None:
    state = ConversationState(id='conversation-123', flow='temporal', messages=[])

    command = build_resume_command('http://127.0.0.1:8000', state, resume_stream=True)

    assert command == (
        'uv run --project apps/api chat --mode temporal '
        '--conversation-id conversation-123 --resume-stream'
    )


def test_format_http_error_prefers_json_detail() -> None:
    request = httpx.Request('GET', 'http://example.com/api')
    response = httpx.Response(500, request=request, json={'detail': 'boom'})
    error = httpx.HTTPStatusError('server error', request=request, response=response)

    assert format_http_error(error) == 'HTTP 500: boom'


def test_stream_chat_events_resume_after_simulated_disconnect() -> None:
    console_output = StringIO()
    console = Console(file=console_output, color_system=None, highlight=False)
    backend = FakeBackend(
        initial_stream=FakeStream(
            'replay-123',
            [SSEFrame(event_id='1-0', payload={'type': 'text-delta', 'delta': 'Hello'})],
        ),
        replay_streams=[
            FakeStream(
                'replay-123',
                [
                    SSEFrame(event_id='1-1', payload={'type': 'text-delta', 'delta': ' world'}),
                    SSEFrame(event_id='1-2', payload={'type': 'finish'}),
                ],
            )
        ],
    )
    state = ConversationState(id='conversation-123', flow='temporal', messages=[])

    events = list(
        stream_chat_events(
            backend,
            console,
            state,
            {'id': 'user-1'},
            StreamOptions(resume_stream=True, debug_stream=True, drop_after_events=1),
        )
    )

    assert events == [
        {'type': 'text-delta', 'delta': 'Hello'},
        {'type': 'text-delta', 'delta': ' world'},
        {'type': 'finish'},
    ]
    assert backend.replay_calls == [('replay-123', '1-0')]
    assert 'replay enabled for temporal' in console_output.getvalue()
    assert 'simulating disconnect after events=' in console_output.getvalue()
    assert 'resuming from last_event_id=' in console_output.getvalue()


def test_stream_chat_events_resume_after_transport_error() -> None:
    request = httpx.Request('GET', 'http://example.com/stream')
    backend = FakeBackend(
        initial_stream=FakeStream(
            'replay-123',
            [
                SSEFrame(event_id='1-0', payload={'type': 'text-delta', 'delta': 'Hello'}),
                httpx.ReadError('stream dropped', request=request),
            ],
        ),
        replay_streams=[
            FakeStream(
                'replay-123',
                [SSEFrame(event_id='1-1', payload={'type': 'text-delta', 'delta': ' again'})],
            )
        ],
    )
    state = ConversationState(id='conversation-123', flow='dbos-replay', messages=[])
    console = Console(file=StringIO(), color_system=None, highlight=False)

    events = list(
        stream_chat_events(
            backend,
            console,
            state,
            {'id': 'user-1'},
            StreamOptions(resume_stream=True),
        )
    )

    assert events == [
        {'type': 'text-delta', 'delta': 'Hello'},
        {'type': 'text-delta', 'delta': ' again'},
    ]
    assert backend.replay_calls == [('replay-123', '1-0')]


def test_stream_chat_events_reject_simulated_disconnect_for_unsupported_flow() -> None:
    backend = FakeBackend(
        initial_stream=FakeStream(
            None,
            [SSEFrame(event_id='1-0', payload={'type': 'text-delta', 'delta': 'Hello'})],
        ),
        replay_streams=[],
    )
    state = ConversationState(id='conversation-123', flow='basic', messages=[])
    console = Console(file=StringIO(), color_system=None, highlight=False)

    with pytest.raises(RuntimeError, match='Simulated disconnects require stream replay'):
        list(
            stream_chat_events(
                backend,
                console,
                state,
                {'id': 'user-1'},
                StreamOptions(resume_stream=True, drop_after_events=1),
            )
        )


def test_stream_chat_events_fail_when_replay_header_is_missing() -> None:
    request = httpx.Request('GET', 'http://example.com/stream')
    backend = FakeBackend(
        initial_stream=FakeStream(
            None,
            [
                SSEFrame(event_id='1-0', payload={'type': 'text-delta', 'delta': 'Hello'}),
                httpx.ReadError('stream dropped', request=request),
            ],
        ),
        replay_streams=[],
    )
    state = ConversationState(id='conversation-123', flow='temporal', messages=[])
    console = Console(file=StringIO(), color_system=None, highlight=False)

    with pytest.raises(RuntimeError, match='Stream replay is unavailable'):
        list(
            stream_chat_events(
                backend,
                console,
                state,
                {'id': 'user-1'},
                StreamOptions(resume_stream=True),
            )
        )
