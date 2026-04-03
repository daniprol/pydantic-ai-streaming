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


json_type = JSON().with_variant(JSONB, 'postgresql')
flow_type_enum = Enum(
    FlowType,
    name='flow_type',
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
