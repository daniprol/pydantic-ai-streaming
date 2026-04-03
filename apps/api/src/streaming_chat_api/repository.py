from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.models import Conversation, FlowType, Message, utcnow


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_conversation(self, flow_type: FlowType) -> Conversation:
        conversation = Conversation(flow_type=flow_type)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_conversation(
        self,
        conversation_id: UUID,
        flow_type: FlowType,
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.flow_type == flow_type,
            )
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        *,
        flow_type: FlowType,
        skip: int,
        limit: int,
    ) -> tuple[list[Conversation], int]:
        base_query: Select[tuple[Conversation]] = select(Conversation).where(
            Conversation.flow_type == flow_type
        )
        total = await self.session.scalar(select(func.count()).select_from(base_query.subquery()))
        result = await self.session.execute(
            base_query.order_by(Conversation.updated_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def delete_conversation(self, conversation_id: UUID, flow_type: FlowType) -> bool:
        conversation = await self.get_conversation(conversation_id, flow_type)
        if conversation is None:
            return False

        await self.session.execute(
            delete(Message).where(Message.conversation_id == conversation_id)
        )
        await self.session.delete(conversation)
        await self.session.flush()
        return True

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence.asc())
        )
        return list(result.scalars().all())

    async def next_sequence(self, conversation_id: UUID) -> int:
        current = await self.session.scalar(
            select(func.max(Message.sequence)).where(Message.conversation_id == conversation_id)
        )
        return int(current or 0) + 1

    async def append_message(
        self,
        *,
        conversation_id: UUID,
        role: str,
        sequence: int,
        ui_message_json: dict,
        model_messages_json: list,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            sequence=sequence,
            ui_message_json=ui_message_json,
            model_messages_json=model_messages_json,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def update_conversation_preview(
        self,
        conversation: Conversation,
        *,
        title: str | None,
        preview: str | None,
    ) -> None:
        if title and not conversation.title:
            conversation.title = title
        if preview:
            conversation.preview = preview
        conversation.updated_at = utcnow()

    async def set_active_replay_id(
        self,
        conversation: Conversation,
        replay_id: str | None,
    ) -> None:
        conversation.active_replay_id = replay_id
        conversation.updated_at = utcnow()

    @staticmethod
    def flatten_model_messages(messages: Sequence[Message]) -> list[dict]:
        model_messages: list[dict] = []
        for message in messages:
            model_messages.extend(message.model_messages_json)
        return model_messages
