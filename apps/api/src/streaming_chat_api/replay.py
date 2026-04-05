from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import redis.asyncio as redis

from streaming_chat_api.settings import Settings


class ReplayStreamBroker:
    def __init__(self, redis_client: redis.Redis, settings: Settings):
        self.redis = redis_client
        self.settings = settings
        self._tasks: set[asyncio.Task[None]] = set()
        self._logger = logging.getLogger(__name__)

    async def append_chunk(self, replay_id: str, chunk: str) -> str:
        stream_key = self._stream_key(replay_id)
        message_id = await self.redis.xadd(stream_key, {'kind': 'chunk', 'payload': chunk})
        await self.redis.expire(stream_key, self.settings.replay_stream_ttl_seconds)
        return message_id

    async def append_complete(self, replay_id: str) -> None:
        stream_key = self._stream_key(replay_id)
        await self.redis.xadd(stream_key, {'kind': 'complete', 'payload': ''})
        await self.redis.expire(stream_key, self.settings.replay_stream_ttl_seconds)

    def start_stream(self, replay_id: str, encoded_stream: AsyncIterator[str]) -> None:
        task = asyncio.create_task(self._publish_stream(replay_id, encoded_stream))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _publish_stream(self, replay_id: str, encoded_stream: AsyncIterator[str]) -> None:
        try:
            async for chunk in encoded_stream:
                await self.append_chunk(replay_id, chunk)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception('Replay stream failed for %s', replay_id)
            await self.append_chunk(replay_id, self._error_event_chunk())
        finally:
            await self.append_complete(replay_id)

    async def replay_stream(self, replay_id: str, last_event_id: str | None) -> AsyncIterator[str]:
        stream_key = self._stream_key(replay_id)
        cursor = last_event_id or '0-0'
        while True:
            try:
                messages = await self.redis.xread({stream_key: cursor}, block=1000, count=100)
            except TypeError:
                messages = await self.redis.xread({stream_key: cursor}, count=100)
                if not messages:
                    await asyncio.sleep(0.1)
                    continue
            if not messages:
                continue
            for _, events in messages:
                for message_id, values in events:
                    cursor = message_id
                    kind = values.get('kind')
                    payload = values.get('payload', '')
                    if kind == 'chunk':
                        yield self._format_sse(message_id, payload)
                    if kind == 'complete':
                        return

    @staticmethod
    def _format_sse(message_id: str, chunk: str) -> str:
        return f'id: {message_id}\n{chunk}'

    @staticmethod
    def _error_event_chunk() -> str:
        payload = json.dumps({'type': 'error', 'errorText': 'Stream replay failed.'})
        return f'data: {payload}\n\n'

    @staticmethod
    def _stream_key(replay_id: str) -> str:
        return f'stream:replay:{replay_id}'
