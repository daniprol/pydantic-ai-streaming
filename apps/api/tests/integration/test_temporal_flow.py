import pytest

from pydantic_ai.ui.vercel_ai import VercelAIAdapter

from streaming_chat_api.services.common import deserialize_model_messages


@pytest.mark.asyncio
async def test_temporal_flow_starts_a_workflow(api_client, resources, chat_request_factory) -> None:
    create_response = await api_client.post('/api/v1/flows/temporal/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await api_client.post(
        f'/api/v1/flows/temporal/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Start a temporal workflow'),
    )
    started_workflows = resources.temporal_client.started_workflows

    assert response.status_code == 200
    assert len(started_workflows) == 1
    assert started_workflows[0]['task_queue'] == resources.settings.temporal_task_queue
    assert started_workflows[0]['workflow'] == 'SupportWorkflow.run'
    assert started_workflows[0]['id'].startswith(f'temporal-chat-{conversation_id}-')
    assert started_workflows[0]['search_attributes'] == {
        'ConversationId': conversation_id,
        'ModelName': 'test',
        'FlowType': 'temporal',
    }
    assert started_workflows[0]['memo'] == {
        'conversation_id': conversation_id,
        'model_name': 'test',
        'flow_type': 'temporal',
    }


@pytest.mark.asyncio
async def test_temporal_flow_includes_current_user_message_in_second_turn(
    api_client,
    resources,
    chat_request_factory,
) -> None:
    create_response = await api_client.post('/api/v1/flows/temporal/conversations')
    conversation_id = create_response.json()['conversation']['id']

    first_response = await api_client.post(
        f'/api/v1/flows/temporal/chat?conversation_id={conversation_id}',
        json=chat_request_factory('hello'),
    )
    second_response = await api_client.post(
        f'/api/v1/flows/temporal/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'call 2 tools with dummy data',
            request_id='request-2',
            message_id='message-2',
        ),
    )

    second_workflow_input = resources.temporal_client.started_workflows[1]['workflow_input']
    messages = VercelAIAdapter.dump_messages(
        deserialize_model_messages(second_workflow_input.message_history)
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert len(resources.temporal_client.started_workflows) == 2
    assert messages[0].role == 'user'
    assert any(message.role == 'assistant' for message in messages[:-1])
    assert messages[-1].role == 'user'
    assert messages[-1].parts[0].text == 'call 2 tools with dummy data'
