from streaming_chat_api.cli import _iter_sse_events


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
