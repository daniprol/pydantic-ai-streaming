from __future__ import annotations

from dataclasses import dataclass

from temporalio import workflow

from pydantic_ai.durable_exec.temporal import PydanticAIWorkflow


@dataclass
class WorkflowInput:
    prompt: str
    conversation_id: str
    session_id: str


@workflow.defn
class SupportWorkflow(PydanticAIWorkflow):
    __pydantic_ai_agents__ = ()

    @workflow.run
    async def run(self, payload: WorkflowInput) -> dict[str, str]:
        return {
            'conversation_id': payload.conversation_id,
            'session_id': payload.session_id,
            'status': 'configured',
        }
