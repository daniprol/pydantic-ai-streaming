from __future__ import annotations

import pytest
from pydantic_ai.exceptions import UserError

from conftest import FakeTaskContext
from pydantic_ai_absurd import AbsurdAgent


async def test_run_inside_existing_absurd_context_does_not_spawn(
    absurd_agent,
    absurd_context,
    deps,
    fake_absurd_app,
) -> None:
    token = absurd_context.set(FakeTaskContext("inline-task"))
    try:
        result = await absurd_agent.run("Where is my order?", deps=deps)
    finally:
        absurd_context.reset(token)

    assert result.output == "done"
    assert fake_absurd_app.spawn_count == 0


async def test_sync_on_complete_runs(fake_absurd_app, base_agent, deps) -> None:
    completions: list[str] = []

    def on_complete(ctx) -> None:
        completions.append(ctx.result.output)

    absurd_agent = AbsurdAgent(
        fake_absurd_app,
        base_agent,
        name="support-agent-absurd",
        on_complete=on_complete,
    )

    result = await absurd_agent.run("Done?", deps=deps)

    assert result.output == "done"
    assert completions == ["done"]


async def test_failing_on_complete_fails_the_task(
    fake_absurd_app, base_agent, deps
) -> None:
    async def on_complete(ctx) -> None:
        raise RuntimeError("persist failed")

    absurd_agent = AbsurdAgent(
        fake_absurd_app,
        base_agent,
        name="support-agent-absurd",
        on_complete=on_complete,
    )

    with pytest.raises(RuntimeError, match="persist failed"):
        await absurd_agent.run("Done?", deps=deps)

    assert fake_absurd_app.last_context is not None
    assert (
        fake_absurd_app.last_context.step_calls[-1]
        == "support-agent-absurd__on_complete"
    )


def test_override_rejects_model_override_inside_durable_context(
    absurd_agent,
    absurd_context,
) -> None:
    token = absurd_context.set(FakeTaskContext("inline-task"))
    try:
        with pytest.raises(UserError, match="Model cannot be contextually overridden"):
            with absurd_agent.override(model=absurd_agent.model):
                pass
    finally:
        absurd_context.reset(token)


def test_override_rejects_tool_override_inside_durable_context(
    absurd_agent,
    absurd_context,
) -> None:
    token = absurd_context.set(FakeTaskContext("inline-task"))
    try:
        with pytest.raises(UserError, match="Tools cannot be contextually overridden"):
            with absurd_agent.override(tools=[]):
                pass
    finally:
        absurd_context.reset(token)
