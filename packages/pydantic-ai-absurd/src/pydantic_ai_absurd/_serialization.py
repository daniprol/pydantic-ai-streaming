from __future__ import annotations

from typing import Any, TypedDict, cast

from pydantic import TypeAdapter
from pydantic_core import to_jsonable_python

import pydantic_ai.messages as _messages
import pydantic_ai.usage as _usage

from pydantic_ai import _agent_graph
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import DeferredToolResults


class SerializedRunParams(TypedDict):
    user_prompt: str | None
    message_history: list[dict[str, Any]]
    deferred_tool_results: dict[str, Any] | None
    deps: Any


class SerializedAgentRunResult(TypedDict):
    output: Any
    output_tool_name: str | None
    message_history: list[dict[str, Any]]
    new_message_index: int
    usage: dict[str, Any]
    run_id: str


_MODEL_RESPONSE_ADAPTER = TypeAdapter(_messages.ModelResponse)
_RUN_USAGE_ADAPTER = TypeAdapter(_usage.RunUsage)
_DEFERRED_TOOL_RESULTS_ADAPTER = TypeAdapter(DeferredToolResults)


def dump_run_params(
    *,
    user_prompt: str | None,
    message_history: list[_messages.ModelMessage] | None,
    deferred_tool_results: DeferredToolResults | None,
    deps_adapter: TypeAdapter[Any],
    deps: Any,
) -> SerializedRunParams:
    return {
        "user_prompt": user_prompt,
        "message_history": _messages.ModelMessagesTypeAdapter.dump_python(
            message_history or [], mode="json"
        ),
        "deferred_tool_results": (
            cast(
                dict[str, Any],
                _DEFERRED_TOOL_RESULTS_ADAPTER.dump_python(
                    deferred_tool_results, mode="json"
                ),
            )
            if deferred_tool_results is not None
            else None
        ),
        "deps": deps_adapter.dump_python(deps, mode="json"),
    }


def load_run_params(
    params: SerializedRunParams, deps_adapter: TypeAdapter[Any]
) -> tuple[
    str | None,
    list[_messages.ModelMessage],
    DeferredToolResults | None,
    Any,
]:
    user_prompt = params["user_prompt"]
    message_history = _messages.ModelMessagesTypeAdapter.validate_python(
        params["message_history"]
    )
    deferred_tool_results = (
        _DEFERRED_TOOL_RESULTS_ADAPTER.validate_python(params["deferred_tool_results"])
        if params["deferred_tool_results"] is not None
        else None
    )
    deps = deps_adapter.validate_python(params["deps"])
    return user_prompt, message_history, deferred_tool_results, deps


def dump_model_response(response: _messages.ModelResponse) -> dict[str, Any]:
    return cast(
        dict[str, Any], _MODEL_RESPONSE_ADAPTER.dump_python(response, mode="json")
    )


def load_model_response(data: dict[str, Any]) -> _messages.ModelResponse:
    return _MODEL_RESPONSE_ADAPTER.validate_python(data)


def dump_agent_run_result(result: AgentRunResult[Any]) -> SerializedAgentRunResult:
    return {
        "output": to_jsonable_python(result.output),
        "output_tool_name": result._output_tool_name,
        "message_history": _messages.ModelMessagesTypeAdapter.dump_python(
            result.all_messages(), mode="json"
        ),
        "new_message_index": result._new_message_index,
        "usage": cast(
            dict[str, Any], _RUN_USAGE_ADAPTER.dump_python(result.usage(), mode="json")
        ),
        "run_id": result.run_id,
    }


def load_agent_run_result(
    data: SerializedAgentRunResult,
    *,
    output_adapter: TypeAdapter[Any],
) -> AgentRunResult[Any]:
    output = output_adapter.validate_python(data["output"])
    state = _agent_graph.GraphAgentState(
        message_history=_messages.ModelMessagesTypeAdapter.validate_python(
            data["message_history"]
        ),
        usage=_RUN_USAGE_ADAPTER.validate_python(data["usage"]),
        run_id=data["run_id"],
    )
    return AgentRunResult(
        output=output,
        _output_tool_name=data["output_tool_name"],
        _state=state,
        _new_message_index=data["new_message_index"],
    )
