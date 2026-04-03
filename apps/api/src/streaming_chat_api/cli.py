from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast
from uuid import uuid4

import httpx
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.pretty import Pretty
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


FlowType = Literal['basic', 'dbos', 'temporal', 'dbos-replay']
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


class ChatBackend(Protocol):
    def list_conversations(self, flow: FlowType) -> list[ConversationSummary]: ...

    def create_conversation(self, flow: FlowType) -> str: ...

    def load_messages(self, flow: FlowType, conversation_id: str) -> list[dict[str, Any]]: ...

    def stream_chat(
        self,
        flow: FlowType,
        conversation_id: str,
        messages: Sequence[dict[str, Any]],
    ) -> Iterator[dict[str, Any]]: ...


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

    def load_messages(self, flow: FlowType, conversation_id: str) -> list[dict[str, Any]]:
        response = self.client.get(f'/api/v1/flows/{flow}/conversations/{conversation_id}/messages')
        response.raise_for_status()
        payload = response.json()
        return cast(list[dict[str, Any]], payload['messages'])

    def stream_chat(
        self,
        flow: FlowType,
        conversation_id: str,
        messages: Sequence[dict[str, Any]],
    ) -> Iterator[dict[str, Any]]:
        request_body = {
            'trigger': 'submit-message',
            'id': f'cli-{conversation_id}',
            'messages': list(messages[-1:]),
        }
        with self.client.stream(
            'POST',
            f'/api/v1/flows/{flow}/chat',
            params={'conversation_id': conversation_id},
            json=request_body,
            headers={'Accept': 'text/event-stream'},
        ) as response:
            response.raise_for_status()
            for event in _iter_sse_events(response.iter_lines()):
                yield event


def _iter_sse_events(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    data_lines: list[str] = []
    for line in lines:
        if not line:
            if data_lines:
                payload = ''.join(data_lines)
                data_lines.clear()
                if payload == '[DONE]':
                    return
                yield cast(dict[str, Any], json.loads(payload))
            continue
        if line.startswith('data: '):
            data_lines.append(line[6:])

    if data_lines:
        payload = ''.join(data_lines)
        if payload != '[DONE]':
            yield cast(dict[str, Any], json.loads(payload))


def build_message(text: str) -> dict[str, Any]:
    return {
        'id': f'user-{uuid4()}',
        'role': 'user',
        'parts': [{'type': 'text', 'text': text}],
    }


def render_message(message: dict[str, Any]) -> list[RenderableType]:
    role = cast(str, message.get('role', 'assistant'))
    renderables: list[RenderableType] = []
    for part in cast(list[dict[str, Any]], message.get('parts', [])):
        part_type = cast(str, part.get('type', ''))
        if part_type == 'text':
            renderables.append(
                Panel(
                    Text(cast(str, part.get('text', '')), style='white'),
                    border_style=ROLE_STYLES.get(role, 'white'),
                    title=role.title(),
                )
            )
            continue
        if part_type == 'reasoning':
            renderables.append(
                Panel(
                    Text(cast(str, part.get('text', '')), style='italic magenta'),
                    border_style='magenta',
                    title='Reasoning',
                )
            )
            continue
        if 'tool' in part_type:
            renderables.append(
                Panel(
                    Pretty(
                        {
                            'tool_name': part.get('tool_name'),
                            'state': part.get('state'),
                            'input': part.get('input'),
                            'output': part.get('output'),
                        },
                        expand_all=True,
                    ),
                    border_style='yellow',
                    title='Tool Call',
                )
            )
    return renderables


class StreamRenderer:
    def __init__(self):
        self.completed: list[RenderableType] = []
        self.current_text = ''
        self.current_reasoning = ''

    def render(self) -> RenderableType:
        renderables = list(self.completed)
        if self.current_reasoning:
            renderables.append(
                Panel(
                    Text(self.current_reasoning, style='italic magenta'),
                    border_style='magenta',
                    title='Thinking',
                )
            )
        if self.current_text:
            renderables.append(
                Panel(
                    Text(self.current_text, style='bold green'),
                    border_style='green',
                    title='Assistant',
                )
            )
        return Group(*renderables) if renderables else Text('')

    def handle_event(self, event: dict[str, Any]) -> None:
        event_type = cast(str, event.get('type', ''))
        if event_type == 'reasoning-delta':
            self.current_reasoning += cast(str, event.get('delta', ''))
            return
        if event_type == 'reasoning-end':
            if self.current_reasoning:
                self.completed.append(
                    Panel(
                        Text(self.current_reasoning, style='italic magenta'),
                        border_style='magenta',
                        title='Thinking',
                    )
                )
                self.current_reasoning = ''
            return
        if event_type == 'text-delta':
            self.current_text += cast(str, event.get('delta', ''))
            return
        if event_type == 'text-end':
            if self.current_text:
                self.completed.append(
                    Panel(
                        Text(self.current_text, style='bold green'),
                        border_style='green',
                        title='Assistant',
                    )
                )
                self.current_text = ''
            return
        if event_type in {'tool-input-start', 'tool-input-available', 'tool-output-available'}:
            self.completed.append(
                Panel(
                    Pretty(event, expand_all=True),
                    border_style='yellow',
                    title='Tool Event',
                )
            )


def print_history(console: Console, state: ConversationState) -> None:
    if not state.messages:
        console.print('[dim]No messages yet.[/dim]')
        return
    console.print(Rule(f'Conversation {state.id}'))
    for message in state.messages:
        for renderable in render_message(message):
            console.print(renderable)


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
        console.print(f'[bold green]Created conversation:[/bold green] {resolved_conversation_id}')
        return ConversationState(id=resolved_conversation_id, flow=flow, messages=[])

    messages = backend.load_messages(flow, resolved_conversation_id)
    console.print(f'[bold blue]Resumed conversation:[/bold blue] {resolved_conversation_id}')
    return ConversationState(id=resolved_conversation_id, flow=flow, messages=messages)


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


def run_chat_loop(backend: ChatBackend, console: Console, state: ConversationState) -> None:
    print_history(console, state)
    console.print('[dim]Commands: /exit, /history, /new[/dim]')

    while True:
        prompt = Prompt.ask('[bold cyan]You[/bold cyan]').strip()
        if not prompt:
            continue
        if prompt in {'/exit', '/quit'}:
            return
        if prompt == '/history':
            state.messages = backend.load_messages(state.flow, state.id)
            print_history(console, state)
            continue
        if prompt == '/new':
            state.id = backend.create_conversation(state.flow)
            state.messages = []
            console.print(f'[bold green]Created conversation:[/bold green] {state.id}')
            continue

        user_message = build_message(prompt)
        console.print(Panel(Text(prompt, style='bold cyan'), border_style='cyan', title='User'))

        renderer = StreamRenderer()
        with Live(renderer.render(), console=console, refresh_per_second=16) as live:
            for event in backend.stream_chat(state.flow, state.id, [user_message]):
                renderer.handle_event(event)
                live.update(renderer.render())

        state.messages = backend.load_messages(state.flow, state.id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Terminal chat client for streaming-chat-api.')
    parser.add_argument(
        '--base-url',
        default='http://127.0.0.1:8000',
        help='Base URL for the API server.',
    )
    parser.add_argument(
        '--mode',
        choices=['basic', 'dbos', 'temporal', 'dbos-replay'],
        default='basic',
        help='Chat flow to use.',
    )
    parser.add_argument('--conversation-id', help='Resume a specific conversation ID.')
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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    console = Console()
    backend = HttpChatBackend(args.base_url)
    try:
        flow = cast(FlowType, args.mode)
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
        run_chat_loop(backend, console, state)
    finally:
        backend.close()


if __name__ == '__main__':
    main()
