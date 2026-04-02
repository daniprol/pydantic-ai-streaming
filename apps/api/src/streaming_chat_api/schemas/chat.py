from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from streaming_chat_api.models.entities import FlowType
from streaming_chat_api.schemas.pagination import PaginatedResponse


class ConversationSummary(BaseModel):
    id: UUID
    flow_type: FlowType
    title: str | None
    preview: str | None
    active_replay_id: str | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(PaginatedResponse[ConversationSummary]):
    pass


class ConversationMessagesResponse(BaseModel):
    conversation_id: UUID
    flow_type: FlowType
    active_replay_id: str | None
    messages: list[dict]


class DeferredToolResultsPayload(BaseModel):
    model_config = ConfigDict(extra='allow')

    calls: dict[str, Any] = Field(default_factory=dict)
    approvals: dict[str, Any] = Field(default_factory=dict)


class ChatRequestEnvelope(BaseModel):
    model_config = ConfigDict(extra='allow')

    trigger: Literal['submit-message', 'regenerate-message'] = 'submit-message'
    id: str | None = None
    message_id: str | None = Field(default=None, alias='messageId')
    messages: list[dict] = Field(default_factory=list)
    deferred_tool_results: DeferredToolResultsPayload | None = Field(
        default=None,
        alias='deferredToolResults',
    )
