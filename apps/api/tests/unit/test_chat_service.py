from pydantic_ai.tools import DeferredToolResults

from streaming_chat_api.schemas.chat import ChatRequestEnvelope
from streaming_chat_api.services.chat import _build_deferred_tool_results


def test_build_deferred_tool_results_from_request_payload() -> None:
    payload = ChatRequestEnvelope.model_validate(
        {
            'trigger': 'submit-message',
            'messages': [],
            'deferredToolResults': {
                'approvals': {'approval-1': True},
                'calls': {'call-1': {'status': 'ok'}},
            },
        }
    )

    result = _build_deferred_tool_results(payload)

    assert isinstance(result, DeferredToolResults)
    assert result.approvals == {'approval-1': True}
    assert result.calls == {'call-1': {'status': 'ok'}}
