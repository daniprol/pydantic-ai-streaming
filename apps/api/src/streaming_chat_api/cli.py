from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast
from uuid import uuid4

import httpx
from rich.console import Console
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


FlowType = Literal['basic', 'dbos', 'temporal', 'dbos-replay']
REPLAYABLE_FLOWS = {'temporal', 'dbos-replay'}
ROLE_STYLES = {
    'user': 'bold cyan',
    'assistant': 'bold green',
    'system': 'bold blue',
}


@dataclass(slots=True)
class ConversationSummary:
    id: str
    title: str | None
    preview: str | None
    updated_at: str


@dataclass(slots=True)
class ConversationState:
    id: str
    flow: FlowType
    messages: list[dict[str, Any]]
    active_replay_id: str | None = None


@dataclass(slots=True)
class ConversationSnapshot:
    messages: list[dict[str, Any]]
    active_replay_id: str | None


@dataclass(slots=True)
class SSEFrame:
    event_id: str | None
    payload: dict[str, Any]


@dataclass(slots=True)
class StreamOptions:
    resume_stream: bool = False
    debug_stream: bool = False
    drop_after_events: int | None = None


class ChatBackend(Protocol):
    def list_conversations(self, flow: FlowType) -> list[ConversationSummary]: ...

    def create_conversation(self, flow: FlowType) -> str: ...

    def load_conversation(self, flow: FlowType, conversation_id: str) -> ConversationSnapshot: ...

    def open_chat_stream(
        self,
        flow: FlowType,
        conversation_id: str,
        messages: Sequence[dict[str, Any]],
    ) -> 'HttpSSEStream': ...

    def open_replay_stream(
        self,
        flow: FlowType,
        replay_id: str,
        last_event_id: str | None,
    ) -> 'HttpSSEStream': ...


class HttpSSEStream(Iterator[SSEFrame]):
    def __init__(self, stream_context: Any):
        self._stream_context = stream_context
        self._response = self._stream_context.__enter__()
        self._closed = False
        try:
            self._response.raise_for_status()
        except Exception:
            self.close()
            raise
        self.replay_id = self._response.headers.get('x-replay-id')
        self._frames = _iter_sse_frames(self._response.iter_lines())

    def __iter__(self) -> 'HttpSSEStream':
        return self

    def __next__(self) -> SSEFrame:
        if self._closed:
            raise StopIteration
        try:
            return next(self._frames)
        except StopIteration:
            self.close()
            raise
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stream_context.__exit__(None, None, None)


class HttpChatBackend:
    def __init__(self, base_url: str):
        self.client = httpx.Client(
            base_url=base_url.rstrip('/'),
            timeout=httpx.Timeout(60.0, read=None),
        )

    def close(self) -> None:
        self.client.close()

    def list_conversations(self, flow: FlowType) -> list[ConversationSummary]:
        response = self.client.get(f'/api/v1/flows/{flow}/conversations')
        response.raise_for_status()
        payload = response.json()
        return [
            ConversationSummary(
                id=item['id'],
                title=item.get('title'),
                preview=item.get('preview'),
                updated_at=item['updated_at'],
            )
            for item in payload['items']
        ]

    def create_conversation(self, flow: FlowType) -> str:
        response = self.client.post(f'/api/v1/flows/{flow}/conversations')
        response.raise_for_status()
        return cast(str, response.json()['conversation']['id'])

    def load_conversation(self, flow: FlowType, conversation_id: str) -> ConversationSnapshot:
        response = self.client.get(f'/api/v1/flows/{flow}/conversations/{conversation_id}/messages')
        response.raise_for_status()
        payload = response.json()
        return ConversationSnapshot(
            messages=cast(list[dict[str, Any]], payload['messages']),
            active_replay_id=cast(str | None, payload.get('active_replay_id')),
        )

    def open_chat_stream(
        self,
        flow: FlowType,
        conversation_id: str,
        messages: Sequence[dict[str, Any]],
    ) -> HttpSSEStream:
        request_body = {
            'trigger': 'submit-message',
            'id': f'cli-{conversation_id}',
            'messages': list(messages[-1:]),
        }
        return self._open_stream(
            'POST',
            f'/api/v1/flows/{flow}/chat',
            params={'conversation_id': conversation_id},
            json=request_body,
            headers={'Accept': 'text/event-stream'},
        )

    def open_replay_stream(
        self,
        flow: FlowType,
        replay_id: str,
        last_event_id: str | None,
    ) -> HttpSSEStream:
        params: dict[str, str] = {}
        if last_event_id is not None:
            params['last_event_id'] = last_event_id
        return self._open_stream(
            'GET',
            f'/api/v1/flows/{flow}/streams/{replay_id}/replay',
            params=params or None,
            headers={'Accept': 'text/event-stream'},
        )

    def _open_stream(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpSSEStream:
        return HttpSSEStream(
            self.client.stream(method, path, params=params, json=json, headers=headers)
        )


def format_http_error(error: httpx.HTTPStatusError) -> str:
    response = error.response
    try:
        message = response.text.strip()
    except httpx.ResponseNotRead:
        response.read()
        message = response.text.strip()
    try:
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get('detail'), str):
            message = payload['detail']
    except ValueError:
        pass

    if not message:
        message = response.reason_phrase or 'Request failed'
    return f'HTTP {response.status_code}: {message}'


def print_api_error(console: Console, error: Exception) -> None:
    if isinstance(error, httpx.HTTPStatusError):
        message = format_http_error(error)
    elif isinstance(error, httpx.RequestError):
        message = f'Request failed: {error}'
    else:
        message = str(error) or error.__class__.__name__
    console.print(Text(message, style='bold red'))


def _iter_sse_frames(lines: Iterable[str]) -> Iterator[SSEFrame]:
    data_lines: list[str] = []
    event_id: str | None = None
    for line in lines:
        if not line:
            if data_lines:
                payload = ''.join(data_lines)
                data_lines.clear()
                if payload == '[DONE]':
                    return
                yield SSEFrame(event_id=event_id, payload=cast(dict[str, Any], json.loads(payload)))
                event_id = None
            continue
        if line.startswith('id: '):
            event_id = line[4:]
            continue
        if line.startswith('data: '):
            data_lines.append(line[6:])

    if data_lines:
        payload = ''.join(data_lines)
        if payload != '[DONE]':
            yield SSEFrame(event_id=event_id, payload=cast(dict[str, Any], json.loads(payload)))


def _iter_sse_events(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    for frame in _iter_sse_frames(lines):
        yield frame.payload


def build_message(text: str) -> dict[str, Any]:
    return {
        'id': f'user-{uuid4()}',
        'role': 'user',
        'parts': [{'type': 'text', 'text': text}],
    }


def _flush_console(console: Console) -> None:
    flush = getattr(console.file, 'flush', None)
    if callable(flush):
        flush()


def _print_inline(console: Console, text: str, *, style: str) -> None:
    rendered = console.get_style(style).render(text, color_system=console.color_system)
    console.file.write(rendered)
    _flush_console(console)


def _print_block(
    console: Console, label: str, text: str, *, label_style: str, text_style: str
) -> None:
    console.print(Text(label, style=label_style))
    console.print(Text(text, style=text_style), soft_wrap=True)


def print_message(console: Console, message: dict[str, Any]) -> None:
    role = cast(str, message.get('role', 'assistant'))
    text_parts: list[str] = []
    for part in cast(list[dict[str, Any]], message.get('parts', [])):
        part_type = cast(str, part.get('type', ''))
        if part_type == 'text':
            text_parts.append(cast(str, part.get('text', '')))
            continue
        if part_type == 'reasoning':
            _print_block(
                console,
                'THINKING:',
                cast(str, part.get('text', '')),
                label_style='italic dim bright_black',
                text_style='italic dim bright_black',
            )
            continue
        if 'tool' in part_type:
            tool_name = cast(str | None, part.get('tool_name')) or cast(
                str | None, part.get('toolName')
            )
            tool_state = cast(str | None, part.get('state'))
            suffix = f' [{tool_state}]' if tool_state else ''
            console.print(Text(f'TOOL: {tool_name or "unknown"}{suffix}', style='yellow'))

    if text_parts:
        label = f'{role.upper()}:'
        _print_block(
            console,
            label,
            '\n'.join(text_parts),
            label_style=ROLE_STYLES.get(role, 'bold white'),
            text_style='white',
        )


def flow_supports_stream_resume(flow: FlowType) -> bool:
    return flow in REPLAYABLE_FLOWS


def print_stream_debug(console: Console, message: str, value: str | None = None) -> None:
    line = Text('[stream]', style='bold magenta')
    line.append(f' {message}', style='bright_black')
    if value is not None:
        line.append(' ', style='bright_black')
        line.append(value, style='bold cyan')
    console.print(line)


class _SimulatedDisconnect(Exception):
    pass


def stream_chat_events(
    backend: ChatBackend,
    console: Console,
    state: ConversationState,
    user_message: dict[str, Any],
    stream_options: StreamOptions,
) -> Iterator[dict[str, Any]]:
    replay_enabled = stream_options.resume_stream and flow_supports_stream_resume(state.flow)
    if stream_options.drop_after_events is not None and not replay_enabled:
        raise RuntimeError(
            'Simulated disconnects require stream replay on temporal or dbos-replay.'
        )

    resume_attempts = 0
    events_seen = 0
    disconnect_simulated = False
    last_event_id: str | None = None
    stream = backend.open_chat_stream(state.flow, state.id, [user_message])
    replay_id = stream.replay_id

    if stream_options.debug_stream and replay_enabled:
        print_stream_debug(console, 'replay enabled for', state.flow)
        if replay_id is not None:
            print_stream_debug(console, 'replay_id=', replay_id)

    while True:
        try:
            for frame in stream:
                if frame.event_id is not None:
                    last_event_id = frame.event_id
                yield frame.payload
                events_seen += 1
                if (
                    stream_options.drop_after_events is not None
                    and not disconnect_simulated
                    and events_seen >= stream_options.drop_after_events
                ):
                    disconnect_simulated = True
                    if stream_options.debug_stream:
                        print_stream_debug(
                            console,
                            'simulating disconnect after events=',
                            str(events_seen),
                        )
                    stream.close()
                    raise _SimulatedDisconnect()
            return
        except (_SimulatedDisconnect, httpx.RequestError):
            stream.close()
            if not replay_enabled or replay_id is None:
                raise RuntimeError('Stream replay is unavailable for this response.')
            if resume_attempts >= 3:
                raise

            resume_attempts += 1
            if stream_options.debug_stream:
                checkpoint = last_event_id or 'stream-start'
                print_stream_debug(console, 'resuming from last_event_id=', checkpoint)
            stream = backend.open_replay_stream(state.flow, replay_id, last_event_id)


class StreamPrinter:
    def __init__(self, console: Console):
        self.console = console
        self.assistant_open = False
        self.thinking_open = False
        self.tool_names: dict[str, str] = {}

    def _end_open_block(self) -> None:
        if self.assistant_open or self.thinking_open:
            self.console.print()
            _flush_console(self.console)
        self.assistant_open = False
        self.thinking_open = False

    def _start_assistant(self) -> None:
        if self.assistant_open:
            return
        self._end_open_block()
        self.console.print(Text('ASSISTANT:', style='bold green'))
        self.assistant_open = True

    def _start_thinking(self) -> None:
        if self.thinking_open:
            return
        self._end_open_block()
        self.console.print(Text('THINKING:', style='italic dim bright_black'))
        self.thinking_open = True

    def handle_event(self, event: dict[str, Any]) -> None:
        event_type = cast(str, event.get('type', ''))
        if event_type == 'reasoning-start':
            self._start_thinking()
            return
        if event_type == 'reasoning-delta':
            self._start_thinking()
            _print_inline(
                self.console, cast(str, event.get('delta', '')), style='italic dim bright_black'
            )
            return
        if event_type == 'reasoning-end':
            self._end_open_block()
            return
        if event_type == 'text-start':
            self._start_assistant()
            return
        if event_type == 'text-delta':
            self._start_assistant()
            _print_inline(self.console, cast(str, event.get('delta', '')), style='green')
            return
        if event_type == 'text-end':
            self._end_open_block()
            return
        if event_type == 'tool-input-start':
            self._end_open_block()
            tool_call_id = cast(str, event.get('toolCallId', ''))
            tool_name = cast(str, event.get('toolName', 'unknown'))
            self.tool_names[tool_call_id] = tool_name
            self.console.print(Text(f'TOOL: {tool_name}', style='yellow'))
            return
        if event_type == 'tool-output-error':
            self._end_open_block()
            tool_name = self.tool_names.get(cast(str, event.get('toolCallId', '')), 'unknown')
            self.console.print(Text(f'TOOL ERROR: {tool_name}', style='bold red'))
            return
        if event_type == 'error':
            self._end_open_block()
            self.console.print(
                Text(f'ERROR: {event.get("errorText", "Unknown stream error")}', style='bold red')
            )
            return
        if event_type in {'finish', 'abort'}:
            self._end_open_block()


def print_history(console: Console, state: ConversationState) -> None:
    if not state.messages:
        console.print(Text('No messages yet.', style='dim'))
        return
    console.print(Rule(f'Conversation {state.id}'))
    for message in state.messages:
        print_message(console, message)


def choose_conversation(
    backend: ChatBackend,
    console: Console,
    flow: FlowType,
    conversation_id: str | None,
    latest: bool,
) -> ConversationState:
    resolved_conversation_id = conversation_id
    if resolved_conversation_id is None and latest:
        conversations = backend.list_conversations(flow)
        resolved_conversation_id = conversations[0].id if conversations else None

    if resolved_conversation_id is None:
        resolved_conversation_id = backend.create_conversation(flow)
        console.print(Text(f'Created conversation: {resolved_conversation_id}', style='bold green'))
        return ConversationState(id=resolved_conversation_id, flow=flow, messages=[])

    snapshot = backend.load_conversation(flow, resolved_conversation_id)
    console.print(Text(f'Resumed conversation: {resolved_conversation_id}', style='bold blue'))
    return ConversationState(
        id=resolved_conversation_id,
        flow=flow,
        messages=snapshot.messages,
        active_replay_id=snapshot.active_replay_id,
    )


def print_conversations_table(
    console: Console, conversations: Sequence[ConversationSummary]
) -> None:
    table = Table(title='Conversations')
    table.add_column('ID', style='cyan')
    table.add_column('Title', style='green')
    table.add_column('Preview', style='white')
    table.add_column('Updated', style='magenta')
    for conversation in conversations:
        table.add_row(
            conversation.id,
            conversation.title or '-',
            conversation.preview or '-',
            conversation.updated_at,
        )
    console.print(table)


def build_resume_command(
    base_url: str,
    state: ConversationState,
    *,
    resume_stream: bool = False,
) -> str:
    command = [
        'uv run --project apps/api chat',
        f'--mode {state.flow}',
        f'--conversation-id {state.id}',
    ]
    if resume_stream:
        command.append('--resume-stream')
    if base_url.rstrip('/') != 'http://127.0.0.1:8000':
        command.append(f'--base-url {base_url}')
    return ' '.join(command)


def print_resume_hint(
    console: Console,
    base_url: str,
    state: ConversationState | None,
    *,
    resume_stream: bool = False,
) -> None:
    console.print()
    if state is None:
        console.print(Text('Interrupted.', style='bold yellow'))
        return

    console.print(Text('Interrupted. Resume with:', style='bold yellow'))
    console.print(
        Text(build_resume_command(base_url, state, resume_stream=resume_stream), style='bold cyan')
    )


def run_chat_loop(
    backend: ChatBackend,
    console: Console,
    state: ConversationState,
    stream_options: StreamOptions,
) -> None:
    print_history(console, state)
    console.print(Text('Commands: /exit, /history, /new', style='dim'))
    if stream_options.resume_stream and not flow_supports_stream_resume(state.flow):
        console.print(
            Text('Stream resume is only supported for temporal and dbos-replay.', style='yellow')
        )

    while True:
        prompt = Prompt.ask('[bold cyan]You[/bold cyan]').strip()
        if not prompt:
            continue
        if prompt in {'/exit', '/quit'}:
            return
        if prompt == '/history':
            try:
                snapshot = backend.load_conversation(state.flow, state.id)
            except httpx.HTTPError as error:
                print_api_error(console, error)
                continue
            state.messages = snapshot.messages
            state.active_replay_id = snapshot.active_replay_id
            print_history(console, state)
            continue
        if prompt == '/new':
            try:
                state.id = backend.create_conversation(state.flow)
            except httpx.HTTPError as error:
                print_api_error(console, error)
                continue
            state.messages = []
            state.active_replay_id = None
            console.print(Text(f'Created conversation: {state.id}', style='bold green'))
            continue

        user_message = build_message(prompt)

        printer = StreamPrinter(console)
        try:
            for event in stream_chat_events(backend, console, state, user_message, stream_options):
                printer.handle_event(event)
            snapshot = backend.load_conversation(state.flow, state.id)
            state.messages = snapshot.messages
            state.active_replay_id = snapshot.active_replay_id
        except httpx.HTTPError as error:
            printer._end_open_block()
            print_api_error(console, error)
        except RuntimeError as error:
            printer._end_open_block()
            console.print(Text(str(error), style='bold red'))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Terminal chat client for streaming-chat-api.')
    parser.add_argument(
        '--base-url',
        default='http://127.0.0.1:8000',
        help='Base URL for the API server.',
    )
    parser.add_argument(
        '-m',
        '--mode',
        choices=['basic', 'dbos', 'temporal', 'dbos-replay'],
        default='basic',
        help='Chat flow to use.',
    )
    parser.add_argument('--conversation-id', '-c', help='Resume a specific conversation ID.')
    parser.add_argument(
        '--latest',
        action='store_true',
        help='Resume the latest conversation for the selected mode.',
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List existing conversations for the selected mode and exit.',
    )
    parser.add_argument(
        '--resume-stream',
        action='store_true',
        help='Automatically resume interrupted streams when the flow supports replay.',
    )
    parser.add_argument(
        '--debug-stream',
        action='store_true',
        help='Show debug output for stream replay checkpoints and reconnects.',
    )
    parser.add_argument(
        '--drop-after-events',
        type=int,
        help='Developer testing: simulate a disconnect after N streamed events.',
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.drop_after_events is not None and not args.resume_stream:
        raise SystemExit('--drop-after-events requires --resume-stream')
    console = Console(highlight=False)
    backend = HttpChatBackend(args.base_url)
    state: ConversationState | None = None
    stream_options = StreamOptions(
        resume_stream=args.resume_stream,
        debug_stream=args.debug_stream,
        drop_after_events=args.drop_after_events,
    )
    try:
        flow = cast(FlowType, args.mode)
        if args.drop_after_events is not None and not flow_supports_stream_resume(flow):
            raise SystemExit('--drop-after-events is only supported for temporal and dbos-replay')
        if args.list:
            print_conversations_table(console, backend.list_conversations(flow))
            return

        state = choose_conversation(
            backend=backend,
            console=console,
            flow=flow,
            conversation_id=args.conversation_id,
            latest=args.latest,
        )
        run_chat_loop(backend, console, state, stream_options)
    except KeyboardInterrupt:
        print_resume_hint(console, args.base_url, state, resume_stream=args.resume_stream)
    except httpx.HTTPError as error:
        print_api_error(console, error)
    finally:
        backend.close()


if __name__ == '__main__':
    main()
