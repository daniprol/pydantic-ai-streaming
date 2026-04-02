from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from pydantic_ai.ui.vercel_ai._event_stream import VERCEL_AI_DSP_HEADERS


def replay_stream_response(stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type='text/event-stream',
        headers=dict(VERCEL_AI_DSP_HEADERS),
    )
