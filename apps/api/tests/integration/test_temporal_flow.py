import pytest


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
