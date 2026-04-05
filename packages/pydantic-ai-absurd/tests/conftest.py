from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from absurd_sdk import TaskResultSnapshot
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai.models.test import TestModel

from pydantic_ai_absurd._agent import AbsurdAgent


@dataclass(slots=True)
class AgentDepsData:
    conversation_id: str


class FakeTaskContext:
    def __init__(self, task_id: str, headers: dict[str, Any] | None = None) -> None:
        self.task_id = task_id
        self._headers = headers or {}
        self._step_counts: dict[str, int] = {}
        self._step_cache: dict[str, Any] = {}
        self.step_calls: list[str] = []

    @property
    def headers(self) -> dict[str, Any]:
        return self._headers

    async def step(self, name: str, fn: Callable[[], Awaitable[Any]]) -> Any:
        count = self._step_counts.get(name, 0) + 1
        self._step_counts[name] = count
        checkpoint_name = name if count == 1 else f"{name}#{count}"
        self.step_calls.append(checkpoint_name)
        if checkpoint_name in self._step_cache:
            return self._step_cache[checkpoint_name]
        result = await fn()
        self._step_cache[checkpoint_name] = result
        return result


class FakeAsyncAbsurd:
    def __init__(self, context_var: ContextVar[FakeTaskContext | None]) -> None:
        self._context_var = context_var
        self._registry: dict[str, dict[str, Any]] = {}
        self._runs: dict[str, dict[str, Any]] = {}
        self.last_context: FakeTaskContext | None = None
        self.spawn_count = 0

    def register_task(self, name: str, queue: str | None = None):
        def decorator(
            handler: Callable[..., Awaitable[Any]],
        ) -> Callable[..., Awaitable[Any]]:
            self._registry[name] = {"handler": handler, "queue": queue}
            return handler

        return decorator

    async def spawn(
        self, task_name: str, params: Any, **_: Any
    ) -> dict[str, str | int]:
        self.spawn_count += 1
        task_id = f"task-{uuid4()}"
        run_id = f"run-{uuid4()}"
        self._runs[task_id] = {
            "task_name": task_name,
            "params": params,
            "run_id": run_id,
        }
        return {"task_id": task_id, "run_id": run_id, "attempt": 1}

    async def await_task_result(
        self, task_id: str, timeout: float | None = None, queue_name: str | None = None
    ):
        run = self._runs[task_id]
        handler = self._registry[run["task_name"]]["handler"]
        ctx = FakeTaskContext(task_id)
        self.last_context = ctx
        token = self._context_var.set(ctx)
        try:
            result = await handler(run["params"], ctx)
            return TaskResultSnapshot(state="completed", result=result)
        except (
            Exception
        ) as exc:  # pragma: no cover - exercised in failure tests if added
            return TaskResultSnapshot(state="failed", failure={"message": str(exc)})
        finally:
            self._context_var.reset(token)


@pytest.fixture
def absurd_context(
    monkeypatch: pytest.MonkeyPatch,
) -> ContextVar[FakeTaskContext | None]:
    context_var: ContextVar[FakeTaskContext | None] = ContextVar(
        "fake_absurd_context", default=None
    )
    monkeypatch.setattr(
        "pydantic_ai_absurd._agent.get_current_context", lambda: context_var.get()
    )
    return context_var


@pytest.fixture
def fake_absurd_app(
    absurd_context: ContextVar[FakeTaskContext | None],
) -> FakeAsyncAbsurd:
    return FakeAsyncAbsurd(absurd_context)


@pytest.fixture
def base_agent() -> Agent[AgentDepsData, str]:
    agent = Agent(
        TestModel(call_tools="all", custom_output_text="done"),
        name="support-agent",
        deps_type=AgentDepsData,
        output_type=str,
    )

    @agent.tool
    async def lookup_order(_: RunContext[AgentDepsData]) -> str:
        return "shipped"

    return agent


@pytest.fixture
def deps() -> AgentDepsData:
    return AgentDepsData(conversation_id="conversation-123")


@pytest.fixture
def absurd_agent(
    fake_absurd_app: FakeAsyncAbsurd, base_agent: Agent[AgentDepsData, str]
) -> AbsurdAgent:
    return AbsurdAgent(fake_absurd_app, base_agent, name="support-agent-absurd")


@pytest.fixture
def captured_events() -> list[AgentStreamEvent]:
    return []
