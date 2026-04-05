from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from absurd_sdk import AsyncTaskContext
from pydantic_core import to_jsonable_python

from pydantic_ai._run_context import AgentDepsT, RunContext
from pydantic_ai.toolsets import WrapperToolset
from pydantic_ai.toolsets.abstract import AbstractToolset, ToolsetTool


def normalize_step_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.<>-]+", "_", value)


@dataclass
class AbsurdToolsetWrapper(WrapperToolset[AgentDepsT]):
    step_name_prefix: str
    get_context: Callable[[], AsyncTaskContext | None]

    @property
    def id(self) -> str | None:
        return self.wrapped.id

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[AgentDepsT],
        tool: ToolsetTool[AgentDepsT],
    ) -> Any:
        absurd_ctx = self.get_context()
        if absurd_ctx is None:
            return await self.wrapped.call_tool(name, tool_args, ctx, tool)

        toolset_name = normalize_step_name(self.id or self.wrapped.label)
        step_name = f"{self.step_name_prefix}__toolset__{toolset_name}.call_tool.{name}"

        async def run_tool() -> Any:
            return to_jsonable_python(
                await self.wrapped.call_tool(name, tool_args, ctx, tool)
            )

        return await absurd_ctx.step(step_name, run_tool)

    def visit_and_replace(
        self,
        visitor: Callable[[AbstractToolset[AgentDepsT]], AbstractToolset[AgentDepsT]],
    ) -> AbstractToolset[AgentDepsT]:
        return self


class AbsurdFunctionToolset(AbsurdToolsetWrapper[AgentDepsT]):
    pass
