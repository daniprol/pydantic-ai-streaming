from __future__ import annotations

import socket
import sys
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from pydantic_ai.run import AgentRunResultEvent

from streaming_chat_api.cli import main
from streaming_chat_api.e2e_server import build_e2e_app


class RunOnlyAgent:
    def __init__(self, inner_agent):
        self._inner_agent = inner_agent

    async def run(
        self,
        *,
        message_history=None,
        deferred_tool_results=None,
        deps=None,
        event_stream_handler=None,
        **kwargs,
    ):
        result = None

        async def event_stream():
            nonlocal result
            async for event in self._inner_agent.run_stream_events(
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                deps=deps,
            ):
                if isinstance(event, AgentRunResultEvent):
                    result = event.result
                else:
                    yield event

        if event_stream_handler is not None:
            await event_stream_handler(None, event_stream())

        assert result is not None
        return result


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_e2e_server() -> Iterator[tuple[str, object]]:
    app = build_e2e_app()
    port = _reserve_port()
    config = uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError('Timed out waiting for e2e server to start')
        time.sleep(0.05)

    try:
        yield f'http://127.0.0.1:{port}', app
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.parametrize('flow', ['dbos-replay', 'temporal'])
def test_cli_replays_streams_end_to_end(
    live_e2e_server: tuple[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flow: str,
) -> None:
    live_e2e_base_url, app = live_e2e_server
    if flow == 'dbos-replay':
        app.state.resources.agents.dbos_replay = RunOnlyAgent(app.state.resources.agents.basic)

    prompts = iter(['Where is my order?', '/exit'])
    monkeypatch.setattr(
        'streaming_chat_api.cli.Prompt.ask', lambda *_args, **_kwargs: next(prompts)
    )
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'chat',
            '--base-url',
            live_e2e_base_url,
            '--mode',
            flow,
            '--resume-stream',
            '--debug-stream',
            '--drop-after-events',
            '3',
        ],
    )

    main()

    output = capsys.readouterr().out
    assert 'ASSISTANT:' in output
    assert 'https://example.com/help/streaming-delays' in output
    assert 'replay enabled for' in output
    assert 'simulating disconnect after events=' in output
    assert 'resuming from last_event_id=' in output


@pytest.mark.parametrize('flow', ['dbos-replay', 'temporal'])
def test_cli_multi_turn_replay_does_not_repeat_previous_answer(
    live_e2e_server: tuple[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flow: str,
) -> None:
    live_e2e_base_url, app = live_e2e_server
    if flow == 'dbos-replay':
        app.state.resources.agents.dbos_replay = RunOnlyAgent(app.state.resources.agents.basic)

    prompts = iter(['hello', 'Where is my order?', '/exit'])
    monkeypatch.setattr(
        'streaming_chat_api.cli.Prompt.ask', lambda *_args, **_kwargs: next(prompts)
    )
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'chat',
            '--base-url',
            live_e2e_base_url,
            '--mode',
            flow,
            '--resume-stream',
            '--debug-stream',
            '--drop-after-events',
            '20',
        ],
    )

    main()

    output = capsys.readouterr().out
    assert output.count('replay_id=') == 2
    assert 'https://example.com/help/streaming-delays' in output
