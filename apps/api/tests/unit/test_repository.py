import pytest

from streaming_chat_api.models import FlowType


@pytest.mark.asyncio
async def test_repository_flattens_messages_in_sequence_order(
    db_session,
    repository_factory,
    conversation_factory,
    message_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(
        db_session,
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


@pytest.mark.asyncio
async def test_repository_delete_removes_conversation_messages_and_listing(
    db_session,
    repository_factory,
    conversation_factory,
    message_factory,
) -> None:
    repository = repository_factory(db_session)
    conversation = await conversation_factory(db_session, flow_type=FlowType.BASIC)
    await message_factory(db_session, conversation_id=conversation.id, sequence=1)
    await db_session.commit()

    deleted = await repository.delete_conversation(conversation.id, FlowType.BASIC)
    await db_session.commit()
    conversations, total = await repository.list_conversations(
        flow_type=FlowType.BASIC, skip=0, limit=20
    )
    messages = await repository.list_messages(conversation.id)

    assert deleted is True
    assert total == 0
    assert conversations == []
    assert messages == []


@pytest.mark.asyncio
async def test_repository_partitions_conversations_by_flow(
    db_session,
    repository_factory,
    conversation_factory,
) -> None:
    repository = repository_factory(db_session)
    await conversation_factory(db_session, flow_type=FlowType.BASIC, title='Basic')
    await conversation_factory(db_session, flow_type=FlowType.TEMPORAL, title='Temporal')
    await db_session.commit()

    basic_conversations, total = await repository.list_conversations(
        flow_type=FlowType.BASIC,
        skip=0,
        limit=20,
    )

    assert total == 1
    assert len(basic_conversations) == 1
    assert basic_conversations[0].flow_type == FlowType.BASIC
