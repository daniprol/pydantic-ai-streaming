from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic_ai.messages import ModelMessage
from pydantic_ai.output import DeferredToolRequests as DeferredToolRequestsOutput
from pydantic_ai.tools import DeferredToolResults, ToolDenied
from pydantic_ai.ui.vercel_ai.request_types import (
    DynamicToolOutputAvailablePart,
    ToolApprovalRespondedPart,
    ToolOutputAvailablePart,
    UIMessage,
)
from pydantic_ai.ui.vercel_ai.request_types import (
    DynamicToolApprovalRespondedPart,
    ToolApprovalResponded,
    ToolApprovalRequested,
)

from streaming_chat_api.models import (
    Conversation,
    PendingToolCall,
    PendingToolCallKind,
    PendingToolCallStatus,
)
from streaming_chat_api.repository import ConversationRepository
from streaming_chat_api.schemas import PendingToolCallResponse
from streaming_chat_api.settings import PendingToolPolicy, Settings


APPROVAL_TOOL_NAMES = {'request_human_approval'}
DECISION_TOOL_NAMES = {'request_human_decision'}
FORM_TOOL_NAMES = {'collect_human_form'}


@dataclass(slots=True)
class PendingToolResolution:
    tool_call_id: str
    status: PendingToolCallStatus
    resolution_json: dict[str, Any]


def classify_pending_tool_call(tool_name: str) -> PendingToolCallKind:
    if tool_name in APPROVAL_TOOL_NAMES:
        return PendingToolCallKind.APPROVAL
    if tool_name in FORM_TOOL_NAMES:
        return PendingToolCallKind.FORM
    if tool_name in DECISION_TOOL_NAMES:
        return PendingToolCallKind.DECISION
    return PendingToolCallKind.DECISION


def build_pending_tool_ui_payload(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    request_metadata: dict[str, Any],
) -> dict[str, Any]:
    kind = classify_pending_tool_call(tool_name)
    if kind == PendingToolCallKind.APPROVAL:
        title = request_metadata.get('title') or 'Approval required'
        description = (
            request_metadata.get('description')
            or tool_args.get('summary')
            or 'Review this action before it runs.'
        )
        return {
            'title': title,
            'description': description,
            'confirmLabel': request_metadata.get('confirmLabel') or 'Approve',
            'rejectLabel': request_metadata.get('rejectLabel') or 'Reject',
        }
    if kind == PendingToolCallKind.FORM:
        return {
            'title': request_metadata.get('title') or tool_args.get('title') or 'Form required',
            'description': request_metadata.get('description')
            or tool_args.get('description')
            or '',
            'schema': tool_args.get('schema') or request_metadata.get('schema') or {'fields': []},
            'submitLabel': request_metadata.get('submitLabel') or 'Submit',
        }
    return {
        'title': request_metadata.get('title') or tool_args.get('title') or 'Decision required',
        'description': request_metadata.get('description') or tool_args.get('description') or '',
        'acceptLabel': request_metadata.get('acceptLabel') or 'Accept',
        'rejectLabel': request_metadata.get('rejectLabel') or 'Reject',
    }


def pending_tool_call_to_response(pending_tool_call: PendingToolCall) -> PendingToolCallResponse:
    return PendingToolCallResponse.model_validate(pending_tool_call)


def pending_policy_blocks_new_message(
    *,
    settings: Settings,
    unresolved_pending_tool_calls: Sequence[PendingToolCall],
    has_new_message: bool,
    has_deferred_tool_results: bool,
) -> bool:
    if not unresolved_pending_tool_calls or not has_new_message:
        return False
    if settings.pending_tool_policy == 'allow_continue':
        return False
    if has_deferred_tool_results:
        return False
    return True


def raise_pending_conflict(unresolved_pending_tool_calls: Sequence[PendingToolCall]) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            'message': 'Resolve pending tool calls before sending a new message.',
            'pending_tool_calls': [
                pending_tool_call_to_response(pending_tool_call).model_dump(mode='json')
                for pending_tool_call in unresolved_pending_tool_calls
            ],
        },
    )


async def persist_pending_tool_calls(
    *,
    repository: ConversationRepository,
    conversation: Conversation,
    requests: DeferredToolRequestsOutput,
    message_sequence: int,
    resume_model_messages: Sequence[ModelMessage],
) -> list[PendingToolCall]:
    pending_group_id = str(uuid4())
    serialized_resume_model_messages = repository.flatten_model_messages([])
    pending_tool_calls: list[PendingToolCall] = []

    from streaming_chat_api.services.common import serialize_model_messages

    serialized_resume_model_messages = serialize_model_messages(resume_model_messages)

    for approval in requests.approvals:
        approval_id = str(uuid4())
        pending_tool_calls.append(
            await repository.create_pending_tool_call(
                conversation_id=conversation.id,
                tool_call_id=approval.tool_call_id,
                pending_group_id=pending_group_id,
                tool_name=approval.tool_name,
                kind=PendingToolCallKind.APPROVAL,
                message_sequence=message_sequence,
                approval_id=approval_id,
                args_json=approval.args_as_dict(),
                request_metadata_json=requests.metadata.get(approval.tool_call_id, {}),
                ui_payload_json=build_pending_tool_ui_payload(
                    tool_name=approval.tool_name,
                    tool_args=approval.args_as_dict(),
                    request_metadata=requests.metadata.get(approval.tool_call_id, {}),
                ),
                resume_model_messages_json=serialized_resume_model_messages,
            )
        )

    for call in requests.calls:
        request_metadata = requests.metadata.get(call.tool_call_id, {})
        pending_tool_calls.append(
            await repository.create_pending_tool_call(
                conversation_id=conversation.id,
                tool_call_id=call.tool_call_id,
                pending_group_id=pending_group_id,
                tool_name=call.tool_name,
                kind=classify_pending_tool_call(call.tool_name),
                message_sequence=message_sequence,
                approval_id=None,
                args_json=call.args_as_dict(),
                request_metadata_json=request_metadata,
                ui_payload_json=build_pending_tool_ui_payload(
                    tool_name=call.tool_name,
                    tool_args=call.args_as_dict(),
                    request_metadata=request_metadata,
                ),
                resume_model_messages_json=serialized_resume_model_messages,
            )
        )

    return pending_tool_calls


def merge_deferred_tool_results(
    adapter_deferred_results,
    parsed_deferred_results,
):
    if adapter_deferred_results is None:
        return parsed_deferred_results
    if parsed_deferred_results is None:
        return adapter_deferred_results

    calls = {**adapter_deferred_results.calls, **parsed_deferred_results.calls}
    approvals = {
        **adapter_deferred_results.approvals,
        **parsed_deferred_results.approvals,
    }
    from pydantic_ai.tools import DeferredToolResults

    return DeferredToolResults(calls=calls, approvals=approvals)


def extract_tool_outputs_from_resume_messages(
    messages: Sequence[UIMessage],
) -> DeferredToolResults | None:
    calls: dict[str, Any] = {}
    approvals: dict[str, Any] = {}

    for message in messages:
        if message.role != 'assistant':
            continue
        for part in message.parts:
            if isinstance(part, ToolOutputAvailablePart | DynamicToolOutputAvailablePart):
                calls[part.tool_call_id] = part.output
            elif isinstance(part, ToolApprovalRespondedPart | DynamicToolApprovalRespondedPart):
                approval = part.approval
                if approval is not None and getattr(approval, 'approved', None) is not None:
                    approvals[part.tool_call_id] = bool(approval.approved)

    if not calls and not approvals:
        return None
    return DeferredToolResults(calls=calls, approvals=approvals)


async def validate_and_resolve_pending_tool_results(
    *,
    repository: ConversationRepository,
    conversation: Conversation,
    deferred_tool_results,
) -> list[PendingToolResolution]:
    if deferred_tool_results is None:
        return []

    resolutions: list[PendingToolResolution] = []

    for tool_call_id, approval_result in deferred_tool_results.approvals.items():
        pending_tool_call = await repository.get_pending_tool_call_by_tool_call_id(
            conversation.id,
            tool_call_id,
        )
        if pending_tool_call is None or pending_tool_call.status != PendingToolCallStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Unknown or resolved pending tool call: {tool_call_id}',
            )
        if approval_result is True:
            resolutions.append(
                PendingToolResolution(
                    tool_call_id=tool_call_id,
                    status=PendingToolCallStatus.RESOLVED,
                    resolution_json={'approved': True},
                )
            )
        elif isinstance(approval_result, ToolDenied):
            resolutions.append(
                PendingToolResolution(
                    tool_call_id=tool_call_id,
                    status=PendingToolCallStatus.DENIED,
                    resolution_json={
                        'approved': False,
                        'reason': approval_result.message,
                    },
                )
            )
        else:
            resolutions.append(
                PendingToolResolution(
                    tool_call_id=tool_call_id,
                    status=PendingToolCallStatus.DENIED,
                    resolution_json={'approved': False},
                )
            )

    for tool_call_id, result in deferred_tool_results.calls.items():
        pending_tool_call = await repository.get_pending_tool_call_by_tool_call_id(
            conversation.id,
            tool_call_id,
        )
        if pending_tool_call is None or pending_tool_call.status != PendingToolCallStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Unknown or resolved pending tool call: {tool_call_id}',
            )
        resolution_status = PendingToolCallStatus.RESOLVED
        if isinstance(result, dict) and result.get('decision') == 'rejected':
            resolution_status = PendingToolCallStatus.DENIED
        resolutions.append(
            PendingToolResolution(
                tool_call_id=tool_call_id,
                status=resolution_status,
                resolution_json={'result': result},
            )
        )

    return resolutions


async def apply_pending_tool_resolutions(
    *,
    repository: ConversationRepository,
    conversation: Conversation,
    resolutions: Sequence[PendingToolResolution],
) -> None:
    for resolution in resolutions:
        pending_tool_call = await repository.get_pending_tool_call_by_tool_call_id(
            conversation.id,
            resolution.tool_call_id,
        )
        if pending_tool_call is None:
            continue
        await repository.resolve_pending_tool_call(
            pending_tool_call,
            status=resolution.status,
            resolution_json=resolution.resolution_json,
        )


def build_approval_requested_ui_message(
    *, assistant_message: dict[str, Any], pending_tool_calls: Sequence[PendingToolCall]
) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    by_tool_call_id = {pending.tool_call_id: pending for pending in pending_tool_calls}

    for part in assistant_message.get('parts', []):
        if not isinstance(part, dict):
            parts.append(part)
            continue
        tool_call_id = part.get('toolCallId') or part.get('tool_call_id')
        pending = by_tool_call_id.get(tool_call_id)
        if pending is None or pending.kind != PendingToolCallKind.APPROVAL:
            parts.append(part)
            continue

        updated_part = dict(part)
        updated_part['state'] = 'approval-requested'
        updated_part['approval'] = ToolApprovalRequested(
            id=pending.approval_id or str(uuid4())
        ).model_dump(mode='json', by_alias=True)
        parts.append(updated_part)

    return {**assistant_message, 'parts': parts}


def hydrate_hitl_ui_message(
    *, assistant_message: dict[str, Any], pending_tool_calls: Sequence[PendingToolCallResponse]
) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    by_tool_call_id = {pending.tool_call_id: pending for pending in pending_tool_calls}

    for part in assistant_message.get('parts', []):
        if not isinstance(part, dict):
            parts.append(part)
            continue

        tool_call_id = part.get('toolCallId') or part.get('tool_call_id')
        pending = by_tool_call_id.get(tool_call_id)
        if pending is None:
            parts.append(part)
            continue

        updated_part = dict(part)
        current_state = updated_part.get('state')

        if pending.kind.value == 'approval' and current_state in {
            'input-available',
            'approval-requested',
        }:
            if pending.status.value == 'pending':
                updated_part['state'] = 'approval-requested'
                updated_part['approval'] = ToolApprovalRequested(
                    id=pending.approval_id or str(uuid4())
                ).model_dump(mode='json', by_alias=True)
            elif pending.status.value == 'resolved':
                updated_part['state'] = 'approval-responded'
                updated_part['approval'] = ToolApprovalResponded(
                    id=pending.approval_id or str(uuid4()),
                    approved=True,
                ).model_dump(mode='json', by_alias=True)
            elif pending.status.value == 'denied':
                updated_part['state'] = 'output-denied'
                updated_part['approval'] = ToolApprovalResponded(
                    id=pending.approval_id or str(uuid4()),
                    approved=False,
                    reason=(pending.resolution_json or {}).get('reason'),
                ).model_dump(mode='json', by_alias=True)
            parts.append(updated_part)
            continue

        if pending.kind.value in {'decision', 'form'} and current_state == 'input-available':
            if pending.status.value == 'resolved':
                updated_part['state'] = 'output-available'
                updated_part['output'] = (pending.resolution_json or {}).get('result')
            elif pending.status.value == 'denied':
                updated_part['state'] = 'output-denied'
            parts.append(updated_part)
            continue

        parts.append(updated_part)

    return {**assistant_message, 'parts': parts}


def build_custom_pending_tool_data_part(pending_tool_call: PendingToolCall) -> dict[str, Any]:
    return {
        'type': 'data-hitl-request',
        'id': pending_tool_call.tool_call_id,
        'data': {
            'toolCallId': pending_tool_call.tool_call_id,
            'toolName': pending_tool_call.tool_name,
            'kind': pending_tool_call.kind.value,
            'status': pending_tool_call.status.value,
            'payload': pending_tool_call.ui_payload_json,
        },
    }


def pending_tool_policy_allows_continue(policy: PendingToolPolicy) -> bool:
    return policy == 'allow_continue'


def result_output_is_deferred_requests(result_output: Any) -> bool:
    return isinstance(result_output, DeferredToolRequestsOutput)
