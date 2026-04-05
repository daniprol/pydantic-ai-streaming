from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias, TypeVar

from pydantic_ai.messages import ModelMessage, UserContent
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import DeferredToolResults

AgentDepsT = TypeVar("AgentDepsT")
OutputDataT = TypeVar("OutputDataT")

ToolStepMode: TypeAlias = Literal["auto", "manual"]


@dataclass(slots=True)
class OnCompleteContext[
    AgentDepsT,
    OutputDataT,
]:
    deps: AgentDepsT
    result: AgentRunResult[OutputDataT]
    absurd_task_id: str
    headers: dict[str, Any]
    user_prompt: str | Sequence[UserContent] | None
    message_history: Sequence[ModelMessage] | None
    deferred_tool_results: DeferredToolResults | None


type OnCompleteHandler[AgentDepsT, OutputDataT] = Callable[
    [OnCompleteContext[AgentDepsT, OutputDataT]], Awaitable[Any] | Any
]
