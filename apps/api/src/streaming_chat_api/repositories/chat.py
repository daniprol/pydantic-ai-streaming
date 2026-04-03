from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from streaming_chat_api.models.entities import (
    ChatConversation,
    ChatMessage,
    ChatSession,
    ChatThread,
    FlowType,
    utcnow,
)


DEFAULT_CHAT_SESSION_CLIENT_ID = 'single-user'


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_session_by_client_id(self, client_id: str) -> ChatSession | None:
        result = await self.session.execute(
            select(ChatSession).where(ChatSession.client_id == client_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_default_session(self) -> ChatSession:
        return await self.get_or_create_session(DEFAULT_CHAT_SESSION_CLIENT_ID)

    async def get_or_create_session(self, client_id: str) -> ChatSession:
        chat_session = await self.get_session_by_client_id(client_id)
        if chat_session is None:
            chat_session = ChatSession(client_id=client_id)
            try:
                async with self.session.begin_nested():
                    self.session.add(chat_session)
                    await self.session.flush()
            except IntegrityError:
                # Another request created the session concurrently.
                chat_session = await self.get_session_by_client_id(client_id)
                assert chat_session is not None
        return chat_session

    async def get_conversation(
        self, conversation_id: UUID, flow_type: FlowType
    ) -> ChatConversation | None:
        result = await self.session.execute(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id,
                ChatConversation.flow_type == flow_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_conversation(
        self,
        *,
        session_id: UUID,
        conversation_id: UUID,
        flow_type: FlowType,
        title: str | None,
        preview: str | None,
    ) -> ChatConversation:
        conversation = await self.get_conversation(conversation_id, flow_type)
        if conversation is None:
            conversation = ChatConversation(
                id=conversation_id,
                session_id=session_id,
                flow_type=flow_type,
                title=title,
                preview=preview,
            )
            self.session.add(conversation)
            await self.session.flush()
        return conversation

    async def get_or_create_thread(self, conversation_id: UUID, flow_type: FlowType) -> ChatThread:
        result = await self.session.execute(
            select(ChatThread).where(ChatThread.conversation_id == conversation_id)
        )
        thread = result.scalar_one_or_none()
        if thread is None:
            thread = ChatThread(conversation_id=conversation_id, flow_type=flow_type)
            self.session.add(thread)
            await self.session.flush()
        return thread

    async def list_conversations(
        self,
        *,
        flow_type: FlowType,
        skip: int,
        limit: int,
    ) -> tuple[list[ChatConversation], int]:
        base_query: Select[tuple[ChatConversation]] = select(ChatConversation).where(
            ChatConversation.flow_type == flow_type,
        )
        total = await self.session.scalar(select(func.count()).select_from(base_query.subquery()))
        result = await self.session.execute(
            base_query.order_by(ChatConversation.updated_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_messages(self, conversation_id: UUID) -> list[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.sequence.asc())
        )
        return list(result.scalars().all())

    async def next_sequence(self, conversation_id: UUID) -> int:
        current = await self.session.scalar(
            select(func.max(ChatMessage.sequence)).where(
                ChatMessage.conversation_id == conversation_id
            )
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
    ) -> ChatMessage:
        message = ChatMessage(
            conversation_id=conversation_id,
            role=role,
            sequence=sequence,
            ui_message_json=ui_message_json,
            model_messages_json=model_messages_json,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def delete_conversation(self, conversation_id: UUID, flow_type: FlowType) -> bool:
        conversation = await self.get_conversation(conversation_id, flow_type)
        if conversation:
            await self.session.execute(delete(ChatMessage).where(ChatMessage.conversation_id == conversation_id))
            await self.session.execute(delete(ChatThread).where(ChatThread.conversation_id == conversation_id))
            await self.session.delete(conversation)
            await self.session.flush()
            return True
        return False

    async def update_conversation_preview(
        self, conversation: ChatConversation, title: str | None, preview: str | None
    ) -> None:
        if title and not conversation.title:
            conversation.title = title
        if preview:
            conversation.preview = preview
        conversation.updated_at = utcnow()

    async def set_active_replay_id(
        self, conversation: ChatConversation, replay_id: str | None
    ) -> None:
        conversation.active_replay_id = replay_id
        conversation.updated_at = utcnow()

    async def update_thread_metadata(
        self,
        thread: ChatThread,
        *,
        workflow_id: str | None = None,
        dbos_workflow_id: str | None = None,
        task_queue: str | None = None,
        replay_id: str | None = None,
        metadata_json: dict | None = None,
    ) -> None:
        thread.workflow_id = workflow_id or thread.workflow_id
        thread.dbos_workflow_id = dbos_workflow_id or thread.dbos_workflow_id
        thread.task_queue = task_queue or thread.task_queue
        thread.replay_id = replay_id or thread.replay_id
        if metadata_json is not None:
            thread.metadata_json = metadata_json
        thread.updated_at = utcnow()

    @staticmethod
    def flatten_model_messages(messages: Sequence[ChatMessage]) -> list[dict]:
        model_messages: list[dict] = []
        for message in messages:
            model_messages.extend(message.model_messages_json)
        return model_messages
