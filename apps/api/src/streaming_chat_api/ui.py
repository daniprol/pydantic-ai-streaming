from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Mapping

from fastapi.responses import StreamingResponse

from pydantic_ai.ui.vercel_ai._event_stream import VERCEL_AI_DSP_HEADERS


def replay_stream_response(
    stream: AsyncIterator[str],
    headers: Mapping[str, str] | None = None,
) -> StreamingResponse:
    response_headers = dict(VERCEL_AI_DSP_HEADERS)
    if headers is not None:
        response_headers.update(headers)
    return StreamingResponse(
        stream,
        media_type='text/event-stream',
        headers=response_headers,
    )
