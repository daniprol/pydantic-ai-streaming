from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

from pydantic_ai.durable_exec.temporal import PydanticAIWorkflow
from pydantic_ai.tools import DeferredToolResults

with workflow.unsafe.imports_passed_through():
    from streaming_chat_api.agents import AgentDependencies
    from streaming_chat_api.services.common import (
        build_temporal_run_metadata,
        deserialize_model_messages,
        serialize_model_messages,
    )
    from streaming_chat_api.temporal_activities import (
        ClearReplayInput,
        FailReplayStreamInput,
        FinalizeReplayStreamInput,
        PersistRunOutputInput,
        clear_temporal_replay,
        fail_temporal_replay_stream,
        finish_temporal_replay_stream,
        persist_temporal_run_output,
    )
    from streaming_chat_api.temporal_runtime import get_temporal_agent


_TEMPORAL_ACTIVITY_TIMEOUT = timedelta(seconds=60)


@dataclass(slots=True)
class WorkflowInput:
    conversation_id: str
    replay_id: str
    request_body: str
    accept: str | None
    message_history: list[dict[str, Any]]
    deferred_tool_results: dict[str, Any] | None = None


def build_temporal_workflow_id(conversation_id: str, replay_id: str) -> str:
    return f'temporal-chat-{conversation_id}-{replay_id}'


def build_temporal_workflow_input(
    *,
    conversation_id: str,
    replay_id: str,
    request_body: bytes,
    accept: str | None,
    message_history: list[dict[str, Any]],
    deferred_tool_results: dict[str, Any] | None,
) -> WorkflowInput:
    return WorkflowInput(
        conversation_id=conversation_id,
        replay_id=replay_id,
        request_body=request_body.decode('utf-8'),
        accept=accept,
        message_history=message_history,
        deferred_tool_results=deferred_tool_results,
    )


@workflow.defn
class SupportWorkflow(PydanticAIWorkflow):
    __pydantic_ai_agents__ = ()

    @workflow.run
    async def run(self, payload: WorkflowInput) -> dict[str, str]:
        agent = get_temporal_agent()
        deferred_tool_results = None
        if payload.deferred_tool_results is not None:
            deferred_tool_results = DeferredToolResults(**payload.deferred_tool_results)

        metadata = build_temporal_run_metadata(
            replay_id=payload.replay_id,
            request_body=payload.request_body.encode('utf-8'),
            accept=payload.accept,
        )

        try:
            result = await agent.run(
                message_history=deserialize_model_messages(payload.message_history),
                deferred_tool_results=deferred_tool_results,
                deps=AgentDependencies(conversation_id=payload.conversation_id),
                metadata=metadata,
            )
            await workflow.execute_activity(
                persist_temporal_run_output,
                args=[
                    PersistRunOutputInput(
                        conversation_id=payload.conversation_id,
                        new_messages=serialize_model_messages(result.new_messages()),
                    )
                ],
                start_to_close_timeout=_TEMPORAL_ACTIVITY_TIMEOUT,
            )
            await workflow.execute_activity(
                finish_temporal_replay_stream,
                args=[
                    FinalizeReplayStreamInput(
                        replay_id=payload.replay_id,
                        request_body=payload.request_body,
                        accept=payload.accept,
                    )
                ],
                start_to_close_timeout=_TEMPORAL_ACTIVITY_TIMEOUT,
            )
            return {
                'conversation_id': payload.conversation_id,
                'replay_id': payload.replay_id,
                'status': 'completed',
            }
        except Exception as exc:
            error_text = str(exc) or exc.__class__.__name__
            await workflow.execute_activity(
                fail_temporal_replay_stream,
                args=[
                    FailReplayStreamInput(
                        replay_id=payload.replay_id,
                        request_body=payload.request_body,
                        accept=payload.accept,
                        error_text=error_text,
                    )
                ],
                start_to_close_timeout=_TEMPORAL_ACTIVITY_TIMEOUT,
            )
            await workflow.execute_activity(
                clear_temporal_replay,
                args=[ClearReplayInput(conversation_id=payload.conversation_id)],
                start_to_close_timeout=_TEMPORAL_ACTIVITY_TIMEOUT,
            )
            raise
