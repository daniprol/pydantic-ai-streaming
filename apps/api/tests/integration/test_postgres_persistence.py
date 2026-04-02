import pytest

from streaming_chat_api.models.entities import FlowType
from streaming_chat_api.repositories.chat import ChatRepository
from uuid import uuid4


@pytest.mark.docker
@pytest.mark.asyncio
async def test_postgres_repository_persists_session_conversation_and_messages(
    postgres_db_session,
    session_factory_fixture,
    conversation_factory,
    message_factory,
) -> None:
    session = await session_factory_fixture(postgres_db_session, client_id='postgres-client')
    conversation = await conversation_factory(
        postgres_db_session,
        session_id=session.id,
        flow_type=FlowType.BASIC,
        title='Persist me',
        preview='Persist me',
    )
    await message_factory(
        postgres_db_session,
        conversation_id=conversation.id,
        role='user',
        sequence=1,
        ui_message_json={'id': 'user-1', 'role': 'user', 'parts': [{'type': 'text', 'text': 'hello'}]},
        model_messages_json=[{'kind': 'request', 'parts': [{'part_kind': 'user-prompt', 'content': 'hello'}]}],
    )
    await postgres_db_session.commit()

    repository = ChatRepository(postgres_db_session)
    conversations, total = await repository.list_conversations(
        session_id=session.id,
        flow_type=FlowType.BASIC,
        page=1,
        page_size=10,
        sort_field='updated_at',
        direction='desc',
    )
    messages = await repository.list_messages(conversation.id)

    assert total == 1
    assert conversations[0].id == conversation.id
    assert messages[0].ui_message_json['id'] == 'user-1'


@pytest.mark.docker
@pytest.mark.asyncio
async def test_postgres_repository_keeps_flow_histories_partitioned(
    postgres_db_session,
    session_factory_fixture,
    conversation_factory,
) -> None:
    session = await session_factory_fixture(postgres_db_session, client_id='partition-client')
    await conversation_factory(
        postgres_db_session,
        session_id=session.id,
        flow_type=FlowType.BASIC,
        title='Basic',
        preview='Basic',
    )
    await conversation_factory(
        postgres_db_session,
        session_id=session.id,
        flow_type=FlowType.DBOS,
        title='Dbos',
        preview='Dbos',
    )
    await postgres_db_session.commit()

    repository = ChatRepository(postgres_db_session)
    basic_conversations, total = await repository.list_conversations(
        session_id=session.id,
        flow_type=FlowType.BASIC,
        page=1,
        page_size=10,
        sort_field='updated_at',
        direction='desc',
    )

    assert total == 1
    assert basic_conversations[0].flow_type == FlowType.BASIC


@pytest.mark.docker
@pytest.mark.asyncio
async def test_postgres_chat_api_persists_messages_and_lists_conversation(
    postgres_api_client,
    chat_request_factory,
) -> None:
    conversation_id = uuid4()

    response = await postgres_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory('Persist this through Postgres'),
        headers={'X-Session-Id': 'postgres-session'},
    )
    conversations = await postgres_api_client.get(
        '/api/v1/flows/basic/conversations',
        headers={'X-Session-Id': 'postgres-session'},
    )
    messages = await postgres_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages',
        headers={'X-Session-Id': 'postgres-session'},
    )

    assert response.status_code == 200
    assert conversations.status_code == 200
    assert conversations.json()['total'] == 1
    assert conversations.json()['items'][0]['id'] == str(conversation_id)
    assert len(messages.json()['messages']) >= 2
