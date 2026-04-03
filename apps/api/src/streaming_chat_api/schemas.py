from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from streaming_chat_api.models import FlowType


T = TypeVar('T')


class OffsetPaginationParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    skip: int
    limit: int
    total: int


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    flow_type: FlowType
    title: str | None
    preview: str | None
    active_replay_id: str | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(PaginatedResponse[ConversationSummary]):
    pass


class ConversationCreateResponse(BaseModel):
    conversation: ConversationSummary


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


class DependencyStatus(BaseModel):
    ok: bool
    detail: str


class HealthStatusResponse(BaseModel):
    uptime_seconds: float
    postgres: DependencyStatus
    redis: DependencyStatus
    temporal: DependencyStatus
    dbos: DependencyStatus
    llm: DependencyStatus
