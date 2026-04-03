import json

import pytest
from fastapi import HTTPException
from pydantic_ai.messages import ModelRequest

from streaming_chat_api.services.common import (
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
    assert messages[0].ui_message_json['parts'][0]['type'] == 'dynamic-tool'
    assert messages[1].ui_message_json['parts'][0]['type'] == 'text'
    assert messages[0].model_messages_json == serialize_model_messages(assistant_messages)
    assert messages[1].model_messages_json == []
    assert repository.flatten_model_messages(messages) == serialize_model_messages(
        assistant_messages
    )
