import pytest

from streaming_chat_api.models import FlowType
from streaming_chat_api.repository import ConversationRepository


@pytest.mark.docker
@pytest.mark.asyncio
async def test_postgres_repository_persists_session_conversation_and_messages(
    postgres_db_session,
    conversation_factory,
    message_factory,
) -> None:
    conversation = await conversation_factory(
        postgres_db_session,
        flow_type=FlowType.BASIC,
        title='Persist me',
        preview='Persist me',
    )
    await message_factory(
        postgres_db_session,
        conversation_id=conversation.id,
        role='user',
        sequence=1,
        ui_message_json={
            'id': 'user-1',
            'role': 'user',
            'parts': [{'type': 'text', 'text': 'hello'}],
        },
        model_messages_json=[
            {'kind': 'request', 'parts': [{'part_kind': 'user-prompt', 'content': 'hello'}]}
        ],
    )
    await postgres_db_session.commit()

    repository = ConversationRepository(postgres_db_session)
    conversations, total = await repository.list_conversations(
        flow_type=FlowType.BASIC,
        skip=0,
        limit=10,
    )
    messages = await repository.list_messages(conversation.id)

    assert total == 1
    assert conversations[0].id == conversation.id
    assert messages[0].ui_message_json['id'] == 'user-1'


@pytest.mark.docker
@pytest.mark.asyncio
async def test_postgres_repository_keeps_flow_histories_partitioned(
    postgres_db_session,
    conversation_factory,
) -> None:
    await conversation_factory(
        postgres_db_session,
        flow_type=FlowType.BASIC,
        title='Basic',
        preview='Basic',
    )
    await conversation_factory(
        postgres_db_session,
        flow_type=FlowType.DBOS,
        title='Dbos',
        preview='Dbos',
    )
    await postgres_db_session.commit()

    repository = ConversationRepository(postgres_db_session)
    basic_conversations, total = await repository.list_conversations(
        flow_type=FlowType.BASIC,
        skip=0,
        limit=10,
    )

    assert total == 1
    assert basic_conversations[0].flow_type == FlowType.BASIC


@pytest.mark.docker
@pytest.mark.asyncio
async def test_postgres_chat_api_persists_messages_and_lists_conversation(
    postgres_api_client,
    chat_request_factory,
) -> None:
    create_response = await postgres_api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await postgres_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Persist this through Postgres'),
    )
    conversations = await postgres_api_client.get('/api/v1/flows/basic/conversations')
    messages = await postgres_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert conversations.status_code == 200
    assert conversations.json()['total'] == 1
    assert conversations.json()['items'][0]['id'] == str(conversation_id)
    assert [message['role'] for message in messages.json()['messages']] == [
        'user',
        'assistant',
        'assistant',
    ]


@pytest.mark.docker
@pytest.mark.asyncio
async def test_postgres_delete_conversation_removes_persisted_messages(
    postgres_api_client,
    chat_request_factory,
) -> None:
    create_response = await postgres_api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']
    await postgres_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Delete in postgres'),
    )

    delete_response = await postgres_api_client.delete(
        f'/api/v1/flows/basic/conversations/{conversation_id}'
    )
    messages = await postgres_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert delete_response.status_code == 204
    assert messages.status_code == 404
