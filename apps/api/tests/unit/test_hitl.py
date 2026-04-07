from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic_ai.tools import DeferredToolResults, ToolDenied

from streaming_chat_api.models import PendingToolCallKind, PendingToolCallStatus
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from streaming_chat_api.services.hitl import (
    build_pending_tool_run_context,
    build_pending_tool_ui_payload,
    extract_tool_outputs_from_resume_messages,
    filter_pending_deferred_tool_results,
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
        request_metadata={
            'fields': [{'kind': 'email', 'label': 'Email', 'name': 'email'}],
            'schema': {'properties': {'fields': {'type': 'array'}}},
        },
    )

    assert payload['title'] == 'Need info'
    assert payload['fields'][0]['name'] == 'email'
    assert payload['schema']['properties']['fields']['type'] == 'array'


def test_pending_policy_blocks_new_message_by_default() -> None:
    settings = build_settings(pending_tool_policy='block')

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


@pytest.mark.asyncio
async def test_validate_and_resolve_pending_tool_results_marks_cancelled_forms(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='form-1',
        pending_group_id='group-1',
        tool_name='collect_human_form',
        kind=PendingToolCallKind.FORM,
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
            calls={'form-1': {'status': 'cancelled'}},
        ),
    )

    assert results[0].status == PendingToolCallStatus.CANCELLED
    assert results[0].resolution_json == {'result': {'status': 'cancelled'}}


@pytest.mark.asyncio
async def test_validate_and_resolve_pending_tool_results_ignores_repeated_deferred_results(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    pending_tool_call = await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='decision-repeat-1',
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
    await repository.resolve_pending_tool_call(
        pending_tool_call,
        status=PendingToolCallStatus.DENIED,
        resolution_json={'result': {'decision': 'rejected'}},
    )

    results = await validate_and_resolve_pending_tool_results(
        repository=repository,
        conversation=conversation,
        deferred_tool_results=DeferredToolResults(
            calls={'decision-repeat-1': {'decision': 'rejected'}},
        ),
    )

    assert results == []


@pytest.mark.asyncio
async def test_validate_and_resolve_pending_tool_results_ignores_repeated_approval_results(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    pending_tool_call = await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='approval-repeat-1',
        pending_group_id='group-1',
        tool_name='request_human_approval',
        kind=PendingToolCallKind.APPROVAL,
        message_sequence=1,
        approval_id='approval-repeat-id',
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[],
    )
    await repository.resolve_pending_tool_call(
        pending_tool_call,
        status=PendingToolCallStatus.RESOLVED,
        resolution_json={'approved': True},
    )

    results = await validate_and_resolve_pending_tool_results(
        repository=repository,
        conversation=conversation,
        deferred_tool_results=DeferredToolResults(
            approvals={'approval-repeat-1': True},
        ),
    )

    assert results == []


@pytest.mark.asyncio
async def test_build_pending_tool_run_context_uses_branch_history_for_resolution(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='decision-branch-1',
        pending_group_id='group-branch-1',
        tool_name='request_human_decision',
        kind=PendingToolCallKind.DECISION,
        message_sequence=2,
        approval_id=None,
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[
            {
                'parts': [{'content': 'branch prompt', 'part_kind': 'user-prompt'}],
                'kind': 'request',
            },
            {
                'kind': 'response',
                'model_name': 'test',
                'parts': [
                    {
                        'tool_call_id': 'decision-branch-1',
                        'tool_name': 'request_human_decision',
                        'args': {'title': 'Decision required'},
                        'part_kind': 'tool-call',
                    }
                ],
            },
        ],
    )

    run_context = await build_pending_tool_run_context(
        repository=repository,
        conversation=conversation,
        current_history=[],
        deferred_tool_results=DeferredToolResults(
            calls={'decision-branch-1': {'decision': 'accepted'}}
        ),
    )

    assert run_context.should_run_agent is True
    assert len(run_context.message_history) == 2
    assert run_context.deferred_tool_results is not None
    assert run_context.deferred_tool_results.calls == {
        'decision-branch-1': {'decision': 'accepted'}
    }


@pytest.mark.asyncio
async def test_build_pending_tool_run_context_skips_agent_when_cancelled_branch_has_follow_up_messages(
    db_session,
    repository_factory,
    conversation_factory,
    message_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    await message_factory(
        db_session,
        conversation_id=conversation.id,
        role='assistant',
        sequence=3,
        ui_message_json={'id': 'assistant-follow-up', 'role': 'assistant'},
        model_messages_json=[],
    )
    await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='form-branch-1',
        pending_group_id='group-branch-1',
        tool_name='collect_human_form',
        kind=PendingToolCallKind.FORM,
        message_sequence=2,
        approval_id=None,
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[
            {
                'parts': [{'content': 'branch prompt', 'part_kind': 'user-prompt'}],
                'kind': 'request',
            },
            {
                'kind': 'response',
                'model_name': 'test',
                'parts': [
                    {
                        'tool_call_id': 'form-branch-1',
                        'tool_name': 'collect_human_form',
                        'args': {'title': 'Form required'},
                        'part_kind': 'tool-call',
                    }
                ],
            },
        ],
    )

    run_context = await build_pending_tool_run_context(
        repository=repository,
        conversation=conversation,
        current_history=[],
        deferred_tool_results=DeferredToolResults(calls={'form-branch-1': {'status': 'cancelled'}}),
    )

    assert run_context.should_run_agent is False
    assert run_context.deferred_tool_results is None


@pytest.mark.asyncio
async def test_build_pending_tool_run_context_keeps_agent_resume_for_cancelled_branch_without_follow_up(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='form-branch-2',
        pending_group_id='group-branch-2',
        tool_name='collect_human_form',
        kind=PendingToolCallKind.FORM,
        message_sequence=2,
        approval_id=None,
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[
            {
                'parts': [{'content': 'branch prompt', 'part_kind': 'user-prompt'}],
                'kind': 'request',
            },
            {
                'kind': 'response',
                'model_name': 'test',
                'parts': [
                    {
                        'tool_call_id': 'form-branch-2',
                        'tool_name': 'collect_human_form',
                        'args': {'title': 'Form required'},
                        'part_kind': 'tool-call',
                    }
                ],
            },
        ],
    )

    run_context = await build_pending_tool_run_context(
        repository=repository,
        conversation=conversation,
        current_history=[],
        deferred_tool_results=DeferredToolResults(calls={'form-branch-2': {'status': 'cancelled'}}),
    )

    assert run_context.should_run_agent is True
    assert run_context.deferred_tool_results is not None


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


def test_extract_tool_outputs_from_resume_messages_collects_cancelled_form_output() -> None:
    results = extract_tool_outputs_from_resume_messages(
        [
            UIMessage.model_validate(
                {
                    'id': 'assistant-form-cancel',
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-collect_human_form',
                            'toolCallId': 'form-call-1',
                            'state': 'output-available',
                            'input': {'title': 'Form required'},
                            'output': {'status': 'cancelled'},
                        },
                    ],
                }
            )
        ]
    )

    assert results is not None
    assert results.calls == {'form-call-1': {'status': 'cancelled'}}


def test_filter_pending_deferred_tool_results_keeps_only_newly_resolved_ids() -> None:
    deferred_tool_results = DeferredToolResults(
        calls={
            'call-1': {'status': 'cancelled'},
            'call-2': {'decision': 'accepted'},
        },
        approvals={'approval-1': True, 'approval-2': False},
        metadata={
            'call-1': {'title': 'Call one'},
            'call-2': {'title': 'Call two'},
            'approval-1': {'title': 'Approval one'},
            'approval-2': {'title': 'Approval two'},
        },
    )

    filtered_results = filter_pending_deferred_tool_results(
        deferred_tool_results,
        [
            type('Resolution', (), {'tool_call_id': 'call-1'})(),
            type('Resolution', (), {'tool_call_id': 'approval-2'})(),
        ],
    )

    assert filtered_results is not None
    assert filtered_results.calls == {'call-1': {'status': 'cancelled'}}
    assert filtered_results.approvals == {'approval-2': False}
    assert filtered_results.metadata == {
        'call-1': {'title': 'Call one'},
        'approval-2': {'title': 'Approval two'},
    }


def test_filter_pending_deferred_tool_results_drops_duplicate_only_payloads() -> None:
    deferred_tool_results = DeferredToolResults(
        calls={'call-1': {'status': 'cancelled'}},
        approvals={},
    )

    filtered_results = filter_pending_deferred_tool_results(deferred_tool_results, [])

    assert filtered_results is None


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
