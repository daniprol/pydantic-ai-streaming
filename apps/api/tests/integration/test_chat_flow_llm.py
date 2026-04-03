import pytest


@pytest.mark.llm
@pytest.mark.asyncio
async def test_basic_flow_streams_with_real_llm(real_api_client, chat_request_factory) -> None:
    create_response = await real_api_client.post('/api/v1/flows/basic/conversations')
    conversation_id = create_response.json()['conversation']['id']

    response = await real_api_client.post(
        f'/api/v1/flows/basic/chat?conversation_id={conversation_id}',
        json=chat_request_factory(
            'Reply with a short plain-text acknowledgement and do not call any tools.'
        ),
    )
    messages = await real_api_client.get(
        f'/api/v1/flows/basic/conversations/{conversation_id}/messages'
    )

    assert response.status_code == 200
    assert response.headers['x-vercel-ai-ui-message-stream'] == 'v1'
    assert response.headers['content-type'].startswith('text/event-stream')
    assert '{"type":"text-delta"' in response.text
    assert 'data: [DONE]' in response.text

    assistant_messages = [
        message for message in messages.json()['messages'] if message['role'] == 'assistant'
    ]
    assistant_text_parts = [
        part['text']
        for message in assistant_messages
        for part in message['parts']
        if part['type'] == 'text'
    ]

    assert assistant_messages
    assert any(text.strip() for text in assistant_text_parts)
