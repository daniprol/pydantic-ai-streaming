from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from streaming_chat_api.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FlowType(StrEnum):
    BASIC = 'basic'
    DBOS = 'dbos'
    TEMPORAL = 'temporal'
    DBOS_REPLAY = 'dbos-replay'


json_type = JSON().with_variant(JSONB, 'postgresql')


class ChatSession(Base):
    __tablename__ = 'chat_session'

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ChatConversation(Base):
    __tablename__ = 'chat_conversation'

    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey('chat_session.id'), index=True)
    flow_type: Mapped[FlowType] = mapped_column(SqlEnum(FlowType, name='flow_type'))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preview: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active_replay_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ChatThread(Base):
    __tablename__ = 'chat_thread'
    __table_args__ = (UniqueConstraint('conversation_id', name='chat_thread_conversation_id_key'),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey('chat_conversation.id'), index=True)
    flow_type: Mapped[FlowType] = mapped_column(SqlEnum(FlowType, name='flow_type'))
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dbos_workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    task_queue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    replay_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(json_type, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ChatMessage(Base):
    __tablename__ = 'chat_message'
    __table_args__ = (
        UniqueConstraint('conversation_id', 'sequence', name='chat_message_conversation_id_sequence_key'),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey('chat_conversation.id'), index=True)
    role: Mapped[str] = mapped_column(String(32))
    sequence: Mapped[int] = mapped_column(Integer())
    ui_message_json: Mapped[dict] = mapped_column(json_type)
    model_messages_json: Mapped[list] = mapped_column(json_type, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
