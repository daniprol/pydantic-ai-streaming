from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any, cast

import pydantic_ai.messages as _messages
import pydantic_ai.models as models
import pydantic_ai.usage as _usage
from absurd_sdk import (
    AsyncAbsurd,
    AsyncTaskContext,
    TaskResultSnapshot,
    get_current_context,
)
from pydantic import TypeAdapter
from typing_extensions import Never

from pydantic_ai import _utils
from pydantic_ai.agent import (
    AbstractAgent,
    AgentRun,
    AgentRunResult,
    WrapperAgent,
)
from pydantic_ai.agent.abstract import EventStreamHandler, Instructions
from pydantic_ai.builtin_tools import AbstractBuiltinTool
from pydantic_ai.exceptions import UserError
from pydantic_ai.models import Model
from pydantic_ai.output import OutputSpec
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.result import StreamedRunResult
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolResults, Tool, ToolFuncEither
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset

from ._fastmcp_toolset import AbsurdFastMCPToolset
from ._function_toolset import AbsurdFunctionToolset
from ._mcp_server import AbsurdMCPServer
from ._model import AbsurdModel
from ._serialization import (
    SerializedRunParams,
    dump_agent_run_result,
    dump_run_params,
    load_agent_run_result,
    load_run_params,
)
from ._types import OnCompleteContext, OnCompleteHandler, ToolStepMode

try:
    from pydantic_ai.mcp import MCPServer
except ImportError:  # pragma: no cover
    MCPServer = None

try:
    from pydantic_ai.toolsets.fastmcp import FastMCPToolset
except ImportError:  # pragma: no cover
    FastMCPToolset = None


class AbsurdAgent(WrapperAgent[Any, Any]):
    def __init__(
        self,
        app: AsyncAbsurd,
        wrapped: AbstractAgent[Any, Any],
        *,
        name: str | None = None,
        event_stream_handler: EventStreamHandler[Any] | None = None,
        tool_step_mode: ToolStepMode = "auto",
        on_complete: OnCompleteHandler[Any, Any] | None = None,
    ):
        super().__init__(wrapped)
        self._app = app
        self._name = name or wrapped.name
        self._event_stream_handler = event_stream_handler
        self._tool_step_mode = tool_step_mode
        self._on_complete = on_complete

        if self._name is None:
            raise UserError(
                "An agent needs to have a unique `name` in order to be used with Absurd. The name will be used to identify the agent task and durable steps."
            )

        self._task_name = f"{self._name}.run"
        registry = getattr(app, "_registry", None)
        if isinstance(registry, dict) and self._task_name in registry:
            raise UserError(
                f"An Absurd task named {self._task_name!r} is already registered."
            )

        self._allow_durable_iter: ContextVar[bool] = ContextVar(
            "_allow_durable_iter", default=False
        )
        self._deps_adapter = TypeAdapter(self.deps_type)
        self._output_adapter = TypeAdapter(self.output_type)

        wrapped_model = wrapped.model
        if wrapped_model is None:
            raise UserError(
                "An agent needs to have a `model` in order to be used with Absurd, it cannot be set at agent run time."
            )

        self._model = AbsurdModel(
            cast(Model, wrapped_model),
            step_name_prefix=self._name,
            get_context=self._get_absurd_context,
            event_stream_handler=self.event_stream_handler,
        )
        self._toolsets = [
            toolset.visit_and_replace(self._absurdify_toolset)
            for toolset in wrapped.toolsets
        ]

        @self._app.register_task(self._task_name)
        async def _run_task(
            params: SerializedRunParams, ctx: AsyncTaskContext
        ) -> dict[str, Any]:
            user_prompt, message_history, deferred_tool_results, deps = load_run_params(
                params, self._deps_adapter
            )
            result = await self._run_with_overrides(
                user_prompt=user_prompt,
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                deps=deps,
            )
            if self._on_complete is not None:
                await ctx.step(
                    f"{self._name}__on_complete",
                    lambda: self._run_on_complete_step(
                        ctx=ctx,
                        deps=deps,
                        result=result,
                        user_prompt=user_prompt,
                        message_history=message_history,
                        deferred_tool_results=deferred_tool_results,
                    ),
                )
            return dump_agent_run_result(result)

        self._run_task = _run_task

    @property
    def app(self) -> AsyncAbsurd:
        return self._app

    @property
    def name(self) -> str | None:
        return self._name

    @name.setter
    def name(self, value: str | None) -> None:  # pragma: no cover
        raise UserError(
            "The agent name cannot be changed after creation. If you need to change the name, create a new agent."
        )

    @property
    def model(self) -> Model:
        return self._model

    @property
    def event_stream_handler(self) -> EventStreamHandler[Any] | None:
        return self._event_stream_handler or super().event_stream_handler

    @property
    def on_complete(self) -> OnCompleteHandler[Any, Any] | None:
        return self._on_complete

    @property
    def toolsets(self) -> Sequence[AbstractToolset[Any]]:
        with self._absurd_overrides():
            return super().toolsets

    def _get_absurd_context(self) -> AsyncTaskContext | None:
        ctx = get_current_context()
        if ctx is None:
            return None
        if isinstance(ctx, AsyncTaskContext):
            return ctx
        if all(hasattr(ctx, attr) for attr in ("step", "task_id", "headers")):
            return cast(AsyncTaskContext, ctx)
        raise UserError(
            "AbsurdAgent currently only supports AsyncAbsurd task execution."
        )

    def _absurdify_toolset(self, toolset: AbstractToolset[Any]) -> AbstractToolset[Any]:
        if self._tool_step_mode != "auto":
            return toolset
        if isinstance(
            toolset, AbsurdFunctionToolset | AbsurdMCPServer | AbsurdFastMCPToolset
        ):
            return toolset
        if isinstance(toolset, FunctionToolset):
            return AbsurdFunctionToolset(
                wrapped=toolset,
                step_name_prefix=self._name,
                get_context=self._get_absurd_context,
            )
        if MCPServer is not None and isinstance(toolset, MCPServer):
            return AbsurdMCPServer(
                wrapped=toolset,
                step_name_prefix=self._name,
                get_context=self._get_absurd_context,
            )
        if FastMCPToolset is not None and isinstance(toolset, FastMCPToolset):
            return AbsurdFastMCPToolset(
                wrapped=toolset,
                step_name_prefix=self._name,
                get_context=self._get_absurd_context,
            )
        return toolset

    @contextmanager
    def _absurd_overrides(self) -> Iterator[None]:
        parallel_mode = getattr(self, "parallel_tool_call_execution_mode", None)
        execution_mode = (
            parallel_mode("sequential")
            if parallel_mode is not None
            else self.sequential_tool_calls()
        )
        with (
            super().override(model=self._model, toolsets=self._toolsets, tools=[]),
            execution_mode,
        ):
            token = self._allow_durable_iter.set(True)
            try:
                yield
            finally:
                self._allow_durable_iter.reset(token)

    def _validate_run_args(
        self,
        *,
        user_prompt: str | Sequence[_messages.UserContent] | None,
        output_type: OutputSpec[Any] | None,
        model: models.Model | models.KnownModelName | str | None,
        instructions: Instructions[Any],
        model_settings: ModelSettings | None,
        usage_limits: _usage.UsageLimits | None,
        usage: _usage.RunUsage | None,
        toolsets: Sequence[AbstractToolset[Any]] | None,
        builtin_tools: Sequence[AbstractBuiltinTool] | None,
        event_stream_handler: EventStreamHandler[Any] | None,
    ) -> str | None:
        unsupported: list[str] = []
        if user_prompt is not None and not isinstance(user_prompt, str):
            unsupported.append("non-string user prompts")
        if output_type is not None:
            unsupported.append("per-run output_type")
        if model is not None:
            unsupported.append("per-run model overrides")
        if instructions is not None:
            unsupported.append("per-run instructions")
        if model_settings is not None:
            unsupported.append("per-run model_settings")
        if usage_limits is not None:
            unsupported.append("per-run usage_limits")
        if usage is not None:
            unsupported.append("per-run usage")
        if toolsets is not None:
            unsupported.append("per-run toolsets")
        if builtin_tools is not None:
            unsupported.append("per-run builtin tools")
        if event_stream_handler is not None:
            unsupported.append("per-run event_stream_handler")
        if unsupported:
            raise UserError(
                f"AbsurdAgent does not support {', '.join(unsupported)}. Configure them at agent creation time instead."
            )
        return cast(str | None, user_prompt)

    async def _run_with_overrides(
        self,
        *,
        user_prompt: str | None,
        message_history: Sequence[_messages.ModelMessage] | None,
        deferred_tool_results: DeferredToolResults | None,
        deps: Any,
    ) -> AgentRunResult[Any]:
        with self._absurd_overrides():
            return await super(WrapperAgent, self).run(
                user_prompt,
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                deps=deps,
                event_stream_handler=self.event_stream_handler,
            )

    async def _run_on_complete_step(
        self,
        *,
        ctx: AsyncTaskContext,
        deps: Any,
        result: AgentRunResult[Any],
        user_prompt: str | None,
        message_history: Sequence[_messages.ModelMessage] | None,
        deferred_tool_results: DeferredToolResults | None,
    ) -> dict[str, bool]:
        assert self._on_complete is not None
        completion_context = OnCompleteContext(
            deps=deps,
            result=result,
            absurd_task_id=ctx.task_id,
            headers=dict(ctx.headers),
            user_prompt=user_prompt,
            message_history=message_history,
            deferred_tool_results=deferred_tool_results,
        )
        completion_result = self._on_complete(completion_context)
        if inspect.isawaitable(completion_result):
            await completion_result
        return {"completed": True}

    def _load_completed_result(
        self, snapshot: TaskResultSnapshot
    ) -> AgentRunResult[Any]:
        if snapshot.state == "completed" and isinstance(snapshot.result, dict):
            return load_agent_run_result(
                snapshot.result, output_adapter=self._output_adapter
            )
        if snapshot.state == "failed":
            raise RuntimeError(f"Absurd task failed: {snapshot.failure}")
        if snapshot.state == "cancelled":
            raise RuntimeError("Absurd task was cancelled.")
        raise RuntimeError(f"Absurd task ended in unexpected state: {snapshot.state}")

    async def run(
        self,
        user_prompt: str | Sequence[_messages.UserContent] | None = None,
        *,
        output_type: OutputSpec[Any] | None = None,
        message_history: Sequence[_messages.ModelMessage] | None = None,
        deferred_tool_results: DeferredToolResults | None = None,
        model: models.Model | models.KnownModelName | str | None = None,
        instructions: Instructions[Any] = None,
        deps: Any = None,
        model_settings: ModelSettings | None = None,
        usage_limits: _usage.UsageLimits | None = None,
        usage: _usage.RunUsage | None = None,
        infer_name: bool = True,
        toolsets: Sequence[AbstractToolset[Any]] | None = None,
        builtin_tools: Sequence[AbstractBuiltinTool] | None = None,
        event_stream_handler: EventStreamHandler[Any] | None = None,
        **_deprecated_kwargs: Never,
    ) -> AgentRunResult[Any]:
        user_prompt = self._validate_run_args(
            user_prompt=user_prompt,
            output_type=output_type,
            model=model,
            instructions=instructions,
            model_settings=model_settings,
            usage_limits=usage_limits,
            usage=usage,
            toolsets=toolsets,
            builtin_tools=builtin_tools,
            event_stream_handler=event_stream_handler,
        )
        absurd_ctx = self._get_absurd_context()
        if absurd_ctx is not None:
            return await self._run_with_overrides(
                user_prompt=user_prompt,
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                deps=deps,
            )

        params = dump_run_params(
            user_prompt=user_prompt,
            message_history=list(message_history or []),
            deferred_tool_results=deferred_tool_results,
            deps_adapter=self._deps_adapter,
            deps=deps,
        )
        spawned = await self._app.spawn(self._task_name, params)
        snapshot = await self._app.await_task_result(spawned["task_id"])
        return self._load_completed_result(snapshot)

    def _raise_streaming_error(self, api_name: str) -> UserError:
        return UserError(
            f"`agent.{api_name}()` cannot be used with AbsurdAgent. Set an `event_stream_handler` on the agent and use `agent.run()` instead."
        )

    @asynccontextmanager
    async def run_stream(
        self, *args: Any, **kwargs: Any
    ) -> AsyncIterator[StreamedRunResult[Any, Any]]:
        raise self._raise_streaming_error("run_stream")
        yield  # pragma: no cover

    def run_stream_events(
        self, *args: Any, **kwargs: Any
    ) -> AsyncIterator[_messages.AgentStreamEvent | AgentRunResultEvent[Any]]:
        raise self._raise_streaming_error("run_stream_events")

    @asynccontextmanager
    async def iter(
        self,
        user_prompt: str | Sequence[_messages.UserContent] | None = None,
        *,
        output_type: OutputSpec[Any] | None = None,
        message_history: Sequence[_messages.ModelMessage] | None = None,
        deferred_tool_results: DeferredToolResults | None = None,
        model: models.Model | models.KnownModelName | str | None = None,
        instructions: Instructions[Any] = None,
        deps: Any = None,
        model_settings: ModelSettings | None = None,
        usage_limits: _usage.UsageLimits | None = None,
        usage: _usage.RunUsage | None = None,
        infer_name: bool = True,
        toolsets: Sequence[AbstractToolset[Any]] | None = None,
        builtin_tools: Sequence[AbstractBuiltinTool] | None = None,
        **_deprecated_kwargs: Never,
    ) -> AsyncIterator[AgentRun[Any, Any]]:
        if not self._allow_durable_iter.get():
            raise self._raise_streaming_error("iter")

        async with super().iter(
            user_prompt=user_prompt,
            output_type=output_type,
            message_history=message_history,
            deferred_tool_results=deferred_tool_results,
            model=model,
            instructions=instructions,
            deps=deps,
            model_settings=model_settings,
            usage_limits=usage_limits,
            usage=usage,
            infer_name=infer_name,
            toolsets=toolsets,
            builtin_tools=builtin_tools,
            **_deprecated_kwargs,
        ) as run:
            yield run

    @contextmanager
    def override(
        self,
        *,
        name: str | _utils.Unset = _utils.UNSET,
        deps: Any | _utils.Unset = _utils.UNSET,
        model: models.Model | models.KnownModelName | str | _utils.Unset = _utils.UNSET,
        toolsets: Sequence[AbstractToolset[Any]] | _utils.Unset = _utils.UNSET,
        tools: Sequence[Tool[Any] | ToolFuncEither[Any, ...]]
        | _utils.Unset = _utils.UNSET,
        instructions: Instructions[Any] | _utils.Unset = _utils.UNSET,
    ) -> Iterator[None]:
        if self._get_absurd_context() is not None:
            if _utils.is_set(model):
                raise UserError(
                    "Model cannot be contextually overridden inside an Absurd task, it must be set at agent creation time."
                )
            if _utils.is_set(toolsets):
                raise UserError(
                    "Toolsets cannot be contextually overridden inside an Absurd task, they must be set at agent creation time."
                )
            if _utils.is_set(tools):
                raise UserError(
                    "Tools cannot be contextually overridden inside an Absurd task, they must be set at agent creation time."
                )
            if _utils.is_set(instructions):
                raise UserError(
                    "Instructions cannot be contextually overridden inside an Absurd task, they must be set at agent creation time."
                )

        with super().override(
            name=name,
            deps=deps,
            model=model,
            toolsets=toolsets,
            tools=tools,
            instructions=instructions,
        ):
            yield
