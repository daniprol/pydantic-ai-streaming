from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai.models.test import TestModel

from pydantic_ai_absurd import AbsurdAgent

from conftest import AgentDepsData


async def test_run_streams_via_event_handler_and_returns_final_result(
    fake_absurd_app,
    deps,
    captured_events: list[AgentStreamEvent],
) -> None:
    agent = Agent(
        TestModel(call_tools="all", custom_output_text="done"),
        name="support-agent",
        deps_type=type(deps),
        output_type=str,
    )

    @agent.tool
    async def lookup_order(_: RunContext[AgentDepsData]) -> str:
        return "shipped"

    async def event_stream_handler(_ctx, stream) -> None:
        async for event in stream:
            captured_events.append(event)

    absurd_agent = AbsurdAgent(
        fake_absurd_app,
        agent,
        name="support-agent-absurd",
        event_stream_handler=event_stream_handler,
    )

    result = await absurd_agent.run("Where is my order?", deps=deps)

    assert result.output == "done"
    assert captured_events
    assert fake_absurd_app.last_context is not None
    assert fake_absurd_app.last_context.step_calls == [
        "support-agent-absurd__model.request_stream",
        "support-agent-absurd__toolset__<agent>.call_tool.lookup_order",
        "support-agent-absurd__model.request_stream#2",
    ]
