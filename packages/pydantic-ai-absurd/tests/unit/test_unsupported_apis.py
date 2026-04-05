from __future__ import annotations

import pytest
from pydantic_ai.exceptions import UserError


@pytest.mark.asyncio
async def test_run_stream_is_unsupported(absurd_agent, deps) -> None:
    with pytest.raises(UserError, match="event_stream_handler"):
        async with absurd_agent.run_stream("Hello", deps=deps):
            pass


@pytest.mark.asyncio
async def test_run_stream_events_is_unsupported(absurd_agent, deps) -> None:
    with pytest.raises(UserError, match="event_stream_handler"):
        async for _ in absurd_agent.run_stream_events("Hello", deps=deps):
            pass


@pytest.mark.asyncio
async def test_iter_is_unsupported(absurd_agent, deps) -> None:
    with pytest.raises(UserError, match="event_stream_handler"):
        async with absurd_agent.iter("Hello", deps=deps):
            pass


@pytest.mark.asyncio
async def test_per_run_event_handler_is_unsupported(absurd_agent, deps) -> None:
    async def handler(ctx, stream):
        async for _ in stream:
            pass

    with pytest.raises(UserError, match="per-run event_stream_handler"):
        await absurd_agent.run("Hello", deps=deps, event_stream_handler=handler)


@pytest.mark.asyncio
async def test_sequence_user_prompt_is_unsupported(absurd_agent, deps) -> None:
    with pytest.raises(UserError, match="non-string user prompts"):
        await absurd_agent.run(["Hello"], deps=deps)
