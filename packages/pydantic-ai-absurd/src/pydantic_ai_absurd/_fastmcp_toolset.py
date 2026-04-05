from __future__ import annotations

from pydantic_ai._run_context import AgentDepsT

from ._function_toolset import AbsurdToolsetWrapper


class AbsurdFastMCPToolset(AbsurdToolsetWrapper[AgentDepsT]):
    pass
