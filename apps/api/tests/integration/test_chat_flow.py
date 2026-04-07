from uuid import UUID

import pytest

from streaming_chat_api.repository import ConversationRepository


@pytest.mark.asyncio
async def test_basic_flow_streams_vercel_events_and_persists_messages(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Where is my order?'),
    )
    conversations = await api_client.get('/api/v1/flows/basic/conversations')
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert response.headers['content-type'].startswith('text/event-stream')
    assert '{"type":"tool-output-available"' in response.text
    assert '{"type":"text-delta"' in response.text
    assert 'https://example.com/help/streaming-delays' in response.text
    assert 'data: [DONE]' in response.text
    assert conversations.status_code == 200
    assert conversations.json()['total'] == 1
    assert conversations.json()['items'][0]['id'] == str(conversation_id)
    assert conversations.json()['items'][0]['title'] == 'Where is my order?'
    assert messages.status_code == 200
    assert messages.json()['conversation_id'] == str(conversation_id)
    assert [message['role'] for message in messages.json()['messages']] == [
        'user',
        'assistant',
        'assistant',
    ]
    assert messages.json()['messages'][1]['parts'][0]['type'].startswith('tool-')
    assert messages.json()['messages'][2]['parts'][0]['type'] == 'text'
    assert (
        'https://example.com/help/streaming-delays'
        in messages.json()['messages'][2]['parts'][0]['text']
    )


@pytest.mark.asyncio
async def test_chat_accepts_deferred_tool_results_without_new_user_message(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-decision] Ask a human to accept or reject whether we should proceed.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-2',
            deferred_tool_results={'calls': {tool_call_id: {'decision': 'accepted'}}},
        ),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_basic_flow_persists_pending_approval_and_exposes_it_in_messages(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-approval] Before doing anything else, ask for human approval to proceed with a refund action.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')

    assert response.status_code == 200
    assert 'tool-approval-request' in response.text
    pending_tool_calls = messages.json()['pending_tool_calls']
    assert len(pending_tool_calls) == 1
    assert pending_tool_calls[0]['kind'] == 'approval'
    assistant_parts = messages.json()['messages'][-1]['parts']
    assert assistant_parts[0]['state'] == 'approval-requested'
    assert assistant_parts[0]['approval']['id'] == pending_tool_calls[0]['approval_id']


@pytest.mark.asyncio
async def test_basic_flow_accepts_native_tool_approval_submission(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-approval] Before doing anything else, ask for human approval to proceed with a refund action.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    assistant_message = messages.json()['messages'][-1]
    pending_tool_call = messages.json()['pending_tool_calls'][0]

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-native-tool-approval',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-request_human_approval',
                            'toolCallId': pending_tool_call['tool_call_id'],
                            'state': 'approval-responded',
                            'input': {'summary': 'Approve refund'},
                            'approval': {
                                'id': pending_tool_call['approval_id'],
                                'approved': True,
                            },
                        }
                    ],
                }
            ],
        ),
    )
    refreshed_messages = await api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert refreshed_messages.json()['pending_tool_calls'][0]['status'] == 'resolved'


@pytest.mark.asyncio
async def test_basic_flow_blocks_new_user_message_while_pending_by_default(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-decision] Ask a human to accept or reject whether we should proceed.'
        ),
    )
    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('A fresh message while pending'),
    )

    assert response.status_code == 409
    assert (
        response.json()['detail']['message']
        == 'Resolve pending tool calls before sending another message.'
    )
    assert response.json()['detail']['pendingToolCallIds']
    assert response.json()['detail']['pending_tool_calls'][0]['kind'] == 'decision'


@pytest.mark.asyncio
async def test_basic_flow_resolves_pending_decision_with_deferred_results(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-decision] Ask a human to accept or reject whether we should proceed.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-2',
            deferred_tool_results={
                'calls': {
                    tool_call_id: {
                        'decision': 'accepted',
                        'reason': 'Proceed',
                    }
                }
            },
        ),
    )
    refreshed_messages = await api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert refreshed_messages.json()['pending_tool_calls'][0]['status'] == 'resolved'


@pytest.mark.asyncio
async def test_basic_flow_accepts_native_tool_output_submission_for_deferred_call(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-decision] Ask a human to accept or reject whether we should proceed.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    assistant_message = messages.json()['messages'][-1]
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-native-tool-output',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-request_human_decision',
                            'toolCallId': tool_call_id,
                            'state': 'output-available',
                            'input': {
                                'title': 'Decision required',
                                'description': 'Choose whether to proceed.',
                            },
                            'output': {'decision': 'accepted'},
                        }
                    ],
                }
            ],
        ),
    )
    refreshed_messages = await api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert refreshed_messages.json()['pending_tool_calls'][0]['status'] == 'resolved'


@pytest.mark.asyncio
async def test_basic_flow_streams_form_payload_data_chunk(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-form] Collect the customer email and notes using the human form tool.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')

    assert response.status_code == 200
    assert 'data-hitl-request' in response.text
    pending_tool_calls = messages.json()['pending_tool_calls']
    assert pending_tool_calls[0]['kind'] == 'form'
    assert pending_tool_calls[0]['ui_payload_json']['fields'][0]['name'] == 'name'
    assert pending_tool_calls[0]['ui_payload_json']['fields'][1]['kind'] == 'email'
    assert (
        pending_tool_calls[0]['ui_payload_json']['schema']['properties']['fields']['type']
        == 'array'
    )


@pytest.mark.asyncio
async def test_basic_flow_marks_cancelled_form_submission_as_cancelled(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-form] Collect the customer onboarding preferences using the human form tool.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    assistant_message = messages.json()['messages'][-1]
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-native-form-cancel',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-collect_human_form',
                            'toolCallId': tool_call_id,
                            'state': 'output-available',
                            'input': {
                                'title': 'New User Onboarding Preference Form',
                                'description': 'Collect onboarding details.',
                            },
                            'output': {'status': 'cancelled'},
                        }
                    ],
                }
            ],
        ),
    )
    refreshed_messages = await api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert refreshed_messages.json()['pending_tool_calls'][0]['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_basic_flow_accepts_new_message_with_cancelled_form_resolution_even_when_pending_blocks(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-form] Collect the customer onboarding preferences using the human form tool.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    assistant_message = messages.json()['messages'][-1]
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']

    response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'What did I do?',
            request_id='request-cancel-and-message',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-collect_human_form',
                            'toolCallId': tool_call_id,
                            'state': 'output-available',
                            'input': {
                                'title': 'Quick info form',
                                'description': 'Collect the minimum customer details before proceeding.',
                            },
                            'output': {'status': 'cancelled'},
                        }
                    ],
                },
                {
                    'id': 'user-next',
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': 'What did I do?'}],
                },
            ],
        ),
    )
    refreshed_messages = await api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert refreshed_messages.json()['pending_tool_calls'][0]['status'] == 'cancelled'
    assert refreshed_messages.json()['messages'][-1]['role'] == 'assistant'


@pytest.mark.asyncio
async def test_basic_flow_accepts_new_message_after_reopening_cancelled_form_resolution(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-form] Collect the customer onboarding preferences using the human form tool.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    assistant_message = messages.json()['messages'][-1]
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']

    cancel_response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-native-form-cancel-reopen',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-collect_human_form',
                            'toolCallId': tool_call_id,
                            'state': 'output-available',
                            'input': {
                                'title': 'Quick info form',
                                'description': 'Collect the minimum customer details before proceeding.',
                            },
                            'output': {'status': 'cancelled'},
                        }
                    ],
                }
            ],
        ),
    )
    reopened_messages = await api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )
    reopened_pending_tool_call = reopened_messages.json()['pending_tool_calls'][0]
    hydrated_assistant_message = next(
        message
        for message in reopened_messages.json()['messages']
        if message['id'] == assistant_message['id']
    )

    follow_up_response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'Did I cancel that form?',
            request_id='request-after-reopen-cancel',
            message_id='user-after-reopen-cancel',
            messages=[
                hydrated_assistant_message,
                {
                    'id': 'user-after-reopen-cancel',
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': 'Did I cancel that form?'}],
                },
            ],
        ),
    )

    assert cancel_response.status_code == 200
    assert reopened_pending_tool_call['status'] == 'cancelled'
    assert hydrated_assistant_message['parts'][0]['state'] == 'output-available'
    assert hydrated_assistant_message['parts'][0]['output'] == {'status': 'cancelled'}
    assert follow_up_response.status_code == 200


@pytest.mark.asyncio
async def test_basic_flow_accepts_real_minimal_cancelled_form_follow_up_request_shape(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-form] Collect the customer onboarding preferences using the human form tool.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    assistant_message = messages.json()['messages'][-1]
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-native-form-cancel-minimal',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-collect_human_form',
                            'toolCallId': tool_call_id,
                            'state': 'output-available',
                            'output': {'status': 'cancelled'},
                        }
                    ],
                }
            ],
        ),
    )

    follow_up_response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json={
            'trigger': 'submit-message',
            'id': str(conversation_id),
            'messages': [
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'output': {'status': 'cancelled'},
                            'state': 'output-available',
                            'toolCallId': tool_call_id,
                            'type': 'tool-collect_human_form',
                        }
                    ],
                },
                {
                    'id': 'user-minimal-follow-up',
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': 'what did i do?'}],
                },
            ],
        },
    )

    assert follow_up_response.status_code == 200


@pytest.mark.asyncio
async def test_basic_flow_accepts_new_message_after_reopening_rejected_decision_resolution(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-decision] Ask a human to accept or reject whether we should proceed.'
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')
    assistant_message = messages.json()['messages'][-1]
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']

    reject_response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-native-decision-reject-reopen',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-request_human_decision',
                            'toolCallId': tool_call_id,
                            'state': 'output-available',
                            'input': {
                                'title': 'Decision required',
                                'description': 'Choose whether to proceed.',
                            },
                            'output': {'decision': 'rejected'},
                        }
                    ],
                }
            ],
        ),
    )
    reopened_messages = await api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )
    reopened_pending_tool_call = reopened_messages.json()['pending_tool_calls'][0]
    hydrated_assistant_message = next(
        message
        for message in reopened_messages.json()['messages']
        if message['id'] == assistant_message['id']
    )

    follow_up_response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'Was that rejected?',
            request_id='request-after-reopen-reject',
            message_id='user-after-reopen-reject',
            messages=[
                hydrated_assistant_message,
                {
                    'id': 'user-after-reopen-reject',
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': 'Was that rejected?'}],
                },
            ],
        ),
    )

    assert reject_response.status_code == 200
    assert reopened_pending_tool_call['status'] == 'denied'
    assert hydrated_assistant_message['parts'][0]['state'] == 'output-available'
    assert hydrated_assistant_message['parts'][0]['output'] == {'decision': 'rejected'}
    assert follow_up_response.status_code == 200


@pytest.mark.asyncio
async def test_basic_flow_allows_new_message_when_pending_policy_is_allow_continue(
    allow_continue_api_client,
    chat_request_factory,
) -> None:
    create_response = await allow_continue_api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await allow_continue_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-decision] Ask a human to accept or reject whether we should proceed.'
        ),
    )
    response = await allow_continue_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Continue anyway'),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_allow_continue_detaches_pending_branch_from_main_model_history(
    allow_continue_api_client,
    allow_continue_resources,
    chat_request_factory,
) -> None:
    create_response = await allow_continue_api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await allow_continue_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-decision] Ask a human to accept or reject whether we should proceed.'
        ),
    )

    async with allow_continue_resources.session_factory() as session:
        repository = ConversationRepository(session)
        messages = await repository.list_messages(UUID(conversation_id))

    assistant_message = next(message for message in messages if message.role == 'assistant')
    assert assistant_message.model_messages_json == []


@pytest.mark.asyncio
async def test_allow_continue_late_cancel_resolution_returns_empty_completion_without_new_assistant_turn(
    allow_continue_api_client,
    chat_request_factory,
) -> None:
    create_response = await allow_continue_api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await allow_continue_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-form] Collect the customer onboarding preferences using the human form tool.'
        ),
    )
    messages = await allow_continue_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )
    assistant_message = messages.json()['messages'][-1]
    tool_call_id = messages.json()['pending_tool_calls'][0]['tool_call_id']

    follow_up_response = await allow_continue_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'Keep chatting while pending', request_id='follow-up-while-pending'
        ),
    )
    cancel_response = await allow_continue_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='late-form-cancel',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-collect_human_form',
                            'toolCallId': tool_call_id,
                            'state': 'output-available',
                            'output': {'status': 'cancelled'},
                        }
                    ],
                }
            ],
        ),
    )
    refreshed_messages = await allow_continue_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert follow_up_response.status_code == 200
    assert cancel_response.status_code == 200
    assert 'data: [DONE]' in cancel_response.text
    assert [message['role'] for message in refreshed_messages.json()['messages']].count(
        'assistant'
    ) == 3
    assert refreshed_messages.json()['pending_tool_calls'][0]['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_allow_continue_late_approval_resolution_resumes_branch_without_follow_up_messages(
    allow_continue_api_client,
    chat_request_factory,
) -> None:
    create_response = await allow_continue_api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    await allow_continue_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            '[hitl-approval] Before doing anything else, ask for human approval to proceed with a refund action.'
        ),
    )
    messages = await allow_continue_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )
    assistant_message = messages.json()['messages'][-1]
    pending_tool_call = messages.json()['pending_tool_calls'][0]

    response = await allow_continue_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='late-approval-accept',
            messages=[
                {
                    'id': assistant_message['id'],
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool-request_human_approval',
                            'toolCallId': pending_tool_call['tool_call_id'],
                            'state': 'approval-responded',
                            'approval': {
                                'id': pending_tool_call['approval_id'],
                                'approved': True,
                            },
                        }
                    ],
                }
            ],
        ),
    )
    refreshed_messages = await allow_continue_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert refreshed_messages.json()['pending_tool_calls'][0]['status'] == 'resolved'
    assert [message['role'] for message in refreshed_messages.json()['messages']].count(
        'assistant'
    ) == 1


@pytest.mark.asyncio
async def test_regenerate_does_not_persist_an_extra_user_message(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    first_response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Please answer twice'),
    )
    regenerate_response = await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            None,
            request_id='request-2',
            trigger='regenerate-message',
        ),
    )
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')

    assert first_response.status_code == 200
    assert regenerate_response.status_code == 200
    assert [message['role'] for message in messages.json()['messages']] == [
        'user',
        'assistant',
        'assistant',
        'assistant',
    ]


@pytest.mark.asyncio
async def test_replay_flow_exposes_replay_endpoint(api_client, chat_request_factory) -> None:
    create_response = await api_client.post('/api/v1/flows/dbos-replay/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/dbos-replay/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Stream this answer'),
    )
    replay = await api_client.get(
        f'/api/v1/flows/dbos-replay/streams/{response.headers["x-replay-id"]}/replay',
        timeout=2,
    )

    assert response.status_code == 200
    assert replay.status_code == 200
    assert replay.headers['content-type'].startswith('text/event-stream')


@pytest.mark.asyncio
async def test_missing_conversation_returns_404(api_client) -> None:
    response = await api_client.get(
        '/api/v1/flows/basic/conversations/87319ab1-c3d1-4e7b-a238-5b932aef2e9a/messages'
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_removes_it_from_list_and_future_reads(
    api_client,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']
    await api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Delete me later'),
    )

    delete_response = await api_client.delete(
        f'/api/v1/flows/basic/conversations/{conversation_id}'
    )
    conversations = await api_client.get('/api/v1/flows/basic/conversations')
    messages = await api_client.get(f'/api/v1/flows/basic/conversations/{conversation_id}/messages')

    assert delete_response.status_code == 204
    assert conversations.json()['items'] == []
    assert messages.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('flow', 'prompt'),
    [
        ('dbos', 'Check the DBOS flow'),
        ('temporal', 'Check the temporal flow'),
    ],
)
async def test_non_replay_flows_persist_messages(
    api_client,
    chat_request_factory,
    flow: str,
    prompt: str,
) -> None:
    create_response = await api_client.post(f'/api/v1/flows/{flow}/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/{flow}/chat?conversation_id={conversation_id}',
        json=chat_request_factory(prompt),
    )
    messages = await api_client.get(
        f'/api/v1/flows/{flow}/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert len(messages.json()['messages']) >= 2
