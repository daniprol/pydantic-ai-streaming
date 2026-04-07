import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic_ai.messages import ModelRequest
from streaming_chat_api.models import FlowType
from streaming_chat_api.schemas import PendingToolCallResponse

from streaming_chat_api.services.common import (
    build_adapter_request_body,
    build_messages_response,
    load_message_history,
    parse_chat_request,
    persist_assistant_messages,
    serialize_model_messages,
)


def test_parse_chat_request_requires_new_message_or_regenerate_or_tool_results(
    chat_request_factory,
) -> None:
    request_body = json.dumps(chat_request_factory(None)).encode()

    with pytest.raises(HTTPException) as exc_info:
        parse_chat_request(request_body)

    assert exc_info.value.status_code == 400


def test_build_adapter_request_body_omits_assistant_resume_messages_from_adapter_payload(
    chat_request_factory,
) -> None:
    request_body = json.dumps(
        chat_request_factory(
            None,
            messages=[
                {
                    'id': 'assistant-1',
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-request_human_decision',
                            'toolCallId': 'tool-1',
                            'state': 'output-available',
                            'input': {'title': 'Decision required'},
                            'output': {'decision': 'accepted'},
                        }
                    ],
                }
            ],
        )
    ).encode()

    parsed_request = parse_chat_request(request_body)
    adapter_request_body = build_adapter_request_body(request_body, parsed_request=parsed_request)

    assert json.loads(adapter_request_body)['messages'] == []


def test_parse_chat_request_keeps_assistant_resume_messages_alongside_new_user_message(
    chat_request_factory,
) -> None:
    request_body = json.dumps(
        chat_request_factory(
            'What did I do?',
            messages=[
                {
                    'id': 'assistant-1',
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-collect_human_form',
                            'toolCallId': 'tool-form-1',
                            'state': 'output-available',
                            'input': {'title': 'Quick info form'},
                            'output': {'status': 'cancelled'},
                        }
                    ],
                },
                {
                    'id': 'user-1',
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': 'What did I do?'}],
                },
            ],
        )
    ).encode()

    parsed_request = parse_chat_request(request_body)

    assert parsed_request.new_message is not None
    assert parsed_request.new_message.role == 'user'
    assert len(parsed_request.resume_messages) == 1
    assert parsed_request.resume_messages[0].role == 'assistant'


def test_parse_chat_request_extracts_explicit_hitl_resolution_payload() -> None:
    request_body = json.dumps(
        {
            'trigger': 'submit-message',
            'messages': [
                {
                    'id': 'user-1',
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': 'What did I do?'}],
                }
            ],
            'hitlResolution': {
                'assistantMessageId': 'assistant-1',
                'tool': 'collect_human_form',
                'toolCallId': 'tool-form-1',
                'output': {'status': 'cancelled'},
            },
        }
    ).encode()

    parsed_request = parse_chat_request(request_body)

    assert parsed_request.new_message is not None
    assert parsed_request.deferred_tool_results is not None
    assert parsed_request.deferred_tool_results.calls == {'tool-form-1': {'status': 'cancelled'}}


def test_build_adapter_request_body_keeps_only_new_user_message_when_assistant_resume_exists(
    chat_request_factory,
) -> None:
    request_body = json.dumps(
        chat_request_factory(
            'What did I do?',
            messages=[
                {
                    'id': 'assistant-1',
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-collect_human_form',
                            'toolCallId': 'tool-form-1',
                            'state': 'output-available',
                            'input': {'title': 'Quick info form'},
                            'output': {'status': 'cancelled'},
                        }
                    ],
                },
                {
                    'id': 'user-1',
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': 'What did I do?'}],
                },
            ],
        )
    ).encode()

    parsed_request = parse_chat_request(request_body)
    adapter_request_body = build_adapter_request_body(request_body, parsed_request=parsed_request)

    messages = json.loads(adapter_request_body)['messages']
    assert len(messages) == 1
    assert messages[0]['id'] == 'user-1'
    assert messages[0]['role'] == 'user'
    assert messages[0]['parts'][0]['type'] == 'text'
    assert messages[0]['parts'][0]['text'] == 'What did I do?'


def test_build_settings_defaults_to_allow_continue_pending_policy() -> None:
    from streaming_chat_api.settings import Settings

    settings = Settings(
        app_env='test',
        app_name='streaming-chat-api-test',
        app_cors_origins=['http://localhost:5173'],
        redis_url='redis://unused',
        use_test_model=True,
    )

    assert settings.pending_tool_policy == 'allow_continue'


@pytest.mark.asyncio
async def test_persist_assistant_messages_stores_all_assistant_ui_messages_once(
    db_session,
    repository_factory,
    conversation_factory,
    support_agent,
    agent_deps_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    deps = agent_deps_factory(conversation_id=str(conversation.id))
    result = await support_agent.run('Check order order-123', deps=deps)
    assistant_messages = list(result.new_messages())
    if assistant_messages and isinstance(assistant_messages[0], ModelRequest):
        assistant_messages = assistant_messages[1:]

    await persist_assistant_messages(
        session=db_session,
        repository=repository,
        conversation=conversation,
        settings=type('SettingsStub', (), {'pending_tool_policy': 'block'})(),
        result=result,
    )

    messages = await repository.list_messages(conversation.id)

    assert [message.role for message in messages] == ['assistant', 'assistant']
    assert messages[0].ui_message_json['parts'][0]['type'].startswith('tool-')
    assert messages[1].ui_message_json['parts'][0]['type'] == 'text'
    assert messages[0].model_messages_json == serialize_model_messages(assistant_messages)
    assert messages[1].model_messages_json == []
    assert repository.flatten_model_messages(messages) == serialize_model_messages(
        assistant_messages
    )


@pytest.mark.asyncio
async def test_load_message_history_strips_pending_branch_messages_when_allow_continue(
    db_session,
    repository_factory,
    conversation_factory,
    message_factory,
) -> None:
    from streaming_chat_api.models import PendingToolCallKind

    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session)
    await message_factory(
        db_session,
        conversation_id=conversation.id,
        role='user',
        sequence=1,
        ui_message_json={
            'id': 'user-1',
            'role': 'user',
            'parts': [{'type': 'text', 'text': 'hello'}],
        },
        model_messages_json=[
            {
                'parts': [{'content': 'hello', 'part_kind': 'user-prompt'}],
                'kind': 'request',
            }
        ],
    )
    await message_factory(
        db_session,
        conversation_id=conversation.id,
        role='assistant',
        sequence=2,
        ui_message_json={'id': 'assistant-pending', 'role': 'assistant'},
        model_messages_json=[
            {
                'kind': 'response',
                'model_name': 'test',
                'parts': [
                    {
                        'tool_call_id': 'pending-1',
                        'tool_name': 'request_human_decision',
                        'args': {'title': 'Decision required'},
                        'part_kind': 'tool-call',
                    }
                ],
            }
        ],
    )
    await repository.create_pending_tool_call(
        conversation_id=conversation.id,
        tool_call_id='pending-1',
        pending_group_id='group-1',
        tool_name='request_human_decision',
        kind=PendingToolCallKind.DECISION,
        message_sequence=2,
        approval_id=None,
        args_json={},
        request_metadata_json={},
        ui_payload_json={},
        resume_model_messages_json=[],
    )

    history = await load_message_history(
        repository,
        conversation.id,
        type('SettingsStub', (), {'pending_tool_policy': 'allow_continue'})(),
    )

    assert len(history) == 1


def test_build_messages_response_hydrates_resolved_hitl_states() -> None:
    now = datetime.now(timezone.utc)
    conversation = type(
        'ConversationStub',
        (),
        {
            'id': uuid4(),
            'flow_type': FlowType.BASIC,
            'active_replay_id': None,
        },
    )()

    response = build_messages_response(
        conversation,
        [
            {
                'id': 'assistant-1',
                'role': 'assistant',
                'parts': [
                    {
                        'type': 'tool-request_human_approval',
                        'toolCallId': 'approval-call-1',
                        'state': 'input-available',
                        'input': {'summary': 'Approve refund'},
                    },
                    {
                        'type': 'tool-request_human_decision',
                        'toolCallId': 'decision-call-1',
                        'state': 'input-available',
                        'input': {'title': 'Decision required'},
                    },
                ],
            }
        ],
        [
            PendingToolCallResponse(
                id=uuid4(),
                tool_call_id='approval-call-1',
                pending_group_id='group-1',
                tool_name='request_human_approval',
                kind='approval',
                status='resolved',
                message_sequence=1,
                approval_id='approval-1',
                args_json={},
                request_metadata_json={},
                ui_payload_json={},
                resolution_json={'approved': True},
                created_at=now,
                resolved_at=now,
            ),
            PendingToolCallResponse(
                id=uuid4(),
                tool_call_id='decision-call-1',
                pending_group_id='group-1',
                tool_name='request_human_decision',
                kind='decision',
                status='resolved',
                message_sequence=1,
                approval_id=None,
                args_json={},
                request_metadata_json={},
                ui_payload_json={},
                resolution_json={'result': {'decision': 'accepted'}},
                created_at=now,
                resolved_at=now,
            ),
        ],
    )

    parts = response.messages[0]['parts']
    assert parts[0]['state'] == 'approval-responded'
    assert parts[0]['approval']['approved'] is True
    assert parts[1]['state'] == 'output-available'
    assert parts[1]['output'] == {'decision': 'accepted'}
