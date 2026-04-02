import pytest

from streaming_chat_api.models.entities import FlowType


@pytest.mark.asyncio
async def test_repository_flattens_messages_in_sequence_order(
    db_session,
    repository_factory,
    session_factory_fixture,
    conversation_factory,
    message_factory,
) -> None:
    repository = repository_factory(db_session)
    chat_session = await session_factory_fixture(db_session, client_id='client-1')
    conversation = await conversation_factory(
        db_session,
        session_id=chat_session.id,
        flow_type=FlowType.BASIC,
        title='First',
        preview='First',
    )
    await message_factory(
        db_session,
        conversation_id=conversation.id,
        role='user',
        sequence=1,
        ui_message_json={'id': '1'},
        model_messages_json=[{'kind': 'request', 'parts': ['a']}],
    )
    await message_factory(
        db_session,
        conversation_id=conversation.id,
        role='assistant',
        sequence=2,
        ui_message_json={'id': '2'},
        model_messages_json=[{'kind': 'response', 'parts': ['b']}],
    )

    messages = await repository.list_messages(conversation.id)

    assert [message.sequence for message in messages] == [1, 2]
    assert repository.flatten_model_messages(messages) == [
        {'kind': 'request', 'parts': ['a']},
        {'kind': 'response', 'parts': ['b']},
    ]
