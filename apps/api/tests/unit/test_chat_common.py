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
