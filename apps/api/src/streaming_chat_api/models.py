from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from streaming_chat_api.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FlowType(StrEnum):
    BASIC = 'basic'
    DBOS = 'dbos'
    TEMPORAL = 'temporal'
    DBOS_REPLAY = 'dbos-replay'


class PendingToolCallKind(StrEnum):
    APPROVAL = 'approval'
    DECISION = 'decision'
    FORM = 'form'


class PendingToolCallStatus(StrEnum):
    PENDING = 'pending'
    RESOLVED = 'resolved'
    DENIED = 'denied'
    CANCELLED = 'cancelled'


json_type = JSON().with_variant(JSONB, 'postgresql')
flow_type_enum = Enum(
    FlowType,
    name='flow_type',
    values_callable=lambda enum: [item.value for item in enum],
)
pending_tool_call_kind_enum = Enum(
    PendingToolCallKind,
    name='pending_tool_call_kind',
    values_callable=lambda enum: [item.value for item in enum],
)
pending_tool_call_status_enum = Enum(
    PendingToolCallStatus,
    name='pending_tool_call_status',
    values_callable=lambda enum: [item.value for item in enum],
)


class Conversation(Base):
    __tablename__ = 'chat_conversation'

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    flow_type: Mapped[FlowType] = mapped_column(flow_type_enum, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preview: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active_replay_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class Message(Base):
    __tablename__ = 'chat_message'
    __table_args__ = (
        UniqueConstraint(
            'conversation_id', 'sequence', name='chat_message_conversation_id_sequence_key'
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey('chat_conversation.id', ondelete='CASCADE'),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32))
    sequence: Mapped[int] = mapped_column(Integer())
    ui_message_json: Mapped[dict] = mapped_column(json_type)
    model_messages_json: Mapped[list] = mapped_column(json_type, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PendingToolCall(Base):
    __tablename__ = 'chat_pending_tool_call'

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey('chat_conversation.id', ondelete='CASCADE'),
        index=True,
    )
    tool_call_id: Mapped[str] = mapped_column(String(255), unique=True)
    pending_group_id: Mapped[str] = mapped_column(String(255), index=True)
    tool_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[PendingToolCallKind] = mapped_column(pending_tool_call_kind_enum)
    status: Mapped[PendingToolCallStatus] = mapped_column(
        pending_tool_call_status_enum,
        default=PendingToolCallStatus.PENDING,
        index=True,
    )
    message_sequence: Mapped[int] = mapped_column(Integer())
    approval_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    args_json: Mapped[dict] = mapped_column(json_type, default=dict)
    request_metadata_json: Mapped[dict] = mapped_column(json_type, default=dict)
    ui_payload_json: Mapped[dict] = mapped_column(json_type, default=dict)
    resolution_json: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    resume_model_messages_json: Mapped[list] = mapped_column(json_type, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
