from __future__ import annotations

from collections.abc import AsyncIterator

import redis.asyncio as redis

from streaming_chat_api.config.settings import Settings


class ReplayStreamBroker:
    def __init__(self, redis_client: redis.Redis, settings: Settings):
        self.redis = redis_client
        self.settings = settings

    async def append_chunk(self, replay_id: str, chunk: str) -> str:
        stream_key = self._stream_key(replay_id)
        message_id = await self.redis.xadd(stream_key, {'kind': 'chunk', 'payload': chunk})
        await self.redis.expire(stream_key, self.settings.redis.replay_stream_ttl_seconds)
        return message_id

    async def append_complete(self, replay_id: str) -> None:
        stream_key = self._stream_key(replay_id)
        await self.redis.xadd(stream_key, {'kind': 'complete', 'payload': ''})
        await self.redis.expire(stream_key, self.settings.redis.replay_stream_ttl_seconds)

    async def live_stream(self, replay_id: str, encoded_stream: AsyncIterator[str]) -> AsyncIterator[str]:
        async for chunk in encoded_stream:
            message_id = await self.append_chunk(replay_id, chunk)
            yield self._format_sse(message_id, chunk)
        await self.append_complete(replay_id)

    async def replay_stream(self, replay_id: str, last_event_id: str | None) -> AsyncIterator[str]:
        stream_key = self._stream_key(replay_id)
        cursor = last_event_id or '0-0'
        while True:
            messages = await self.redis.xread({stream_key: cursor}, block=1000, count=100)
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
    def _stream_key(replay_id: str) -> str:
        return f'stream:replay:{replay_id}'
