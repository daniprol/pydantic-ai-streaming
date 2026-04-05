from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

from pydantic_ai_absurd import AbsurdAgent

from conftest import AgentDepsData


async def test_run_wraps_model_and_tools_as_steps(fake_absurd_app, deps) -> None:
    tool_calls: list[str] = []
    agent = Agent(
        TestModel(call_tools="all", custom_output_text="done"),
        name="support-agent",
        deps_type=type(deps),
        output_type=str,
    )

    @agent.tool
    async def lookup_order(_: RunContext[AgentDepsData]) -> str:
        tool_calls.append("lookup_order")
        return "shipped"

    absurd_agent = AbsurdAgent(fake_absurd_app, agent, name="support-agent-absurd")

    result = await absurd_agent.run("Where is my order?", deps=deps)

    assert result.output == "done"
    assert tool_calls == ["lookup_order"]
    assert fake_absurd_app.last_context is not None
    assert fake_absurd_app.last_context.step_calls == [
        "support-agent-absurd__model.request",
        "support-agent-absurd__toolset__<agent>.call_tool.lookup_order",
        "support-agent-absurd__model.request#2",
    ]


async def test_manual_tool_step_mode_leaves_tools_unwrapped(
    fake_absurd_app, deps
) -> None:
    tool_calls: list[str] = []
    agent = Agent(
        TestModel(call_tools="all", custom_output_text="done"),
        name="support-agent",
        deps_type=type(deps),
        output_type=str,
    )

    @agent.tool
    async def lookup_order(_: RunContext[AgentDepsData]) -> str:
        tool_calls.append("lookup_order")
        return "shipped"

    absurd_agent = AbsurdAgent(
        fake_absurd_app,
        agent,
        name="support-agent-absurd",
        tool_step_mode="manual",
    )

    result = await absurd_agent.run("Where is my order?", deps=deps)

    assert result.output == "done"
    assert tool_calls == ["lookup_order"]
    assert fake_absurd_app.last_context is not None
    assert fake_absurd_app.last_context.step_calls == [
        "support-agent-absurd__model.request",
        "support-agent-absurd__model.request#2",
    ]


async def test_on_complete_runs_in_final_step(
    fake_absurd_app, base_agent, deps
) -> None:
    completed: list[tuple[str, str]] = []

    async def on_complete(ctx) -> None:
        completed.append((ctx.absurd_task_id, ctx.result.output))

    absurd_agent = AbsurdAgent(
        fake_absurd_app,
        base_agent,
        name="support-agent-absurd",
        on_complete=on_complete,
    )

    result = await absurd_agent.run("Done?", deps=deps)

    assert result.output == "done"
    assert fake_absurd_app.last_context is not None
    assert completed == [(fake_absurd_app.last_context.task_id, "done")]
    assert (
        fake_absurd_app.last_context.step_calls[-1]
        == "support-agent-absurd__on_complete"
    )
