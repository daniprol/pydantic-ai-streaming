from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic_ai.tools import DeferredToolResults, ToolDenied

from streaming_chat_api.models import PendingToolCallKind, PendingToolCallStatus
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from streaming_chat_api.services.hitl import (
    build_pending_tool_ui_payload,
    extract_tool_outputs_from_resume_messages,
    pending_policy_blocks_new_message,
    raise_pending_conflict,
    validate_and_resolve_pending_tool_results,
)
from streaming_chat_api.settings import Settings


def build_settings(**overrides) -> Settings:
    return Settings(
        app_env='test',
        app_name='streaming-chat-api-test',
        app_cors_origins=['http://localhost:5173'],
        redis_url='redis://unused',
        use_test_model=True,
        **overrides,
    )


def test_build_pending_tool_ui_payload_classifies_form_payload() -> None:
    payload = build_pending_tool_ui_payload(
        tool_name='collect_human_form',
        tool_args={'title': 'Need info'},
        request_metadata={'schema': {'fields': [{'name': 'email'}]}},
    )

    assert payload['title'] == 'Need info'
    assert payload['schema']['fields'][0]['name'] == 'email'


def test_pending_policy_blocks_new_message_by_default() -> None:
    settings = build_settings()

    blocked = pending_policy_blocks_new_message(
        settings=settings,
        unresolved_pending_tool_calls=[object()],
        has_new_message=True,
        has_deferred_tool_results=False,
    )

    assert blocked is True


def test_pending_policy_allows_new_message_when_configured() -> None:
    settings = build_settings(pending_tool_policy='allow_continue')

    blocked = pending_policy_blocks_new_message(
        settings=settings,
        unresolved_pending_tool_calls=[object()],
        has_new_message=True,
        has_deferred_tool_results=False,
    )

    assert blocked is False


@pytest.mark.asyncio
async def test_raise_pending_conflict_returns_pending_payload(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    pending_tool_call = await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='tool-1',
        pending_group_id='group-1',
        tool_name='request_human_decision',
        kind=PendingToolCallKind.DECISION,
        message_sequence=1,
        approval_id=None,
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        raise_pending_conflict([pending_tool_call])

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail['pending_tool_calls'][0]['tool_call_id'] == 'tool-1'


@pytest.mark.asyncio
async def test_validate_and_resolve_pending_tool_results_handles_approval_and_call(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='approval-1',
        pending_group_id='group-1',
        tool_name='request_human_approval',
        kind=PendingToolCallKind.APPROVAL,
        message_sequence=1,
        approval_id='approval-id-1',
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[],
    )
    await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='call-1',
        pending_group_id='group-1',
        tool_name='request_human_decision',
        kind=PendingToolCallKind.DECISION,
        message_sequence=1,
        approval_id=None,
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[],
    )

    results = await validate_and_resolve_pending_tool_results(
        repository=repository,
        conversation=conversation,
        deferred_tool_results=DeferredToolResults(
            approvals={'approval-1': ToolDenied('No')},
            calls={'call-1': {'decision': 'accepted'}},
        ),
    )

    assert {result.tool_call_id for result in results} == {'approval-1', 'call-1'}
    denied = next(result for result in results if result.tool_call_id == 'approval-1')
    assert denied.status == PendingToolCallStatus.DENIED


def test_extract_tool_outputs_from_resume_messages_collects_approval_and_call_results() -> None:
    results = extract_tool_outputs_from_resume_messages(
        [
            UIMessage.model_validate(
                {
                    'id': 'assistant-1',
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-request_human_approval',
                            'toolCallId': 'approval-call-1',
                            'state': 'approval-responded',
                            'input': {'summary': 'Approve refund'},
                            'approval': {'id': 'approval-1', 'approved': True},
                        },
                        {
                            'type': 'tool-request_human_decision',
                            'toolCallId': 'decision-call-1',
                            'state': 'output-available',
                            'input': {'title': 'Decision required'},
                            'output': {'decision': 'accepted'},
                        },
                    ],
                }
            )
        ]
    )

    assert results is not None
    assert results.approvals == {'approval-call-1': True}
    assert results.calls == {'decision-call-1': {'decision': 'accepted'}}


@pytest.mark.asyncio
async def test_raise_pending_conflict_includes_simplified_ids(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    pending_tool_call = await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='tool-simple',
        pending_group_id='group-1',
        tool_name='request_human_decision',
        kind=PendingToolCallKind.DECISION,
        message_sequence=1,
        approval_id=None,
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        raise_pending_conflict([pending_tool_call])

    assert exc_info.value.detail['pendingToolCallIds'] == ['tool-simple']
