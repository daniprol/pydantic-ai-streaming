"""initial chat schema

Revision ID: 20260402_initial_chat_schema
Revises:
Create Date: 2026-04-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260402_initial_chat_schema'
down_revision = None
branch_labels = None
depends_on = None


flow_type = sa.Enum('basic', 'dbos', 'temporal', 'dbos-replay', name='flow_type')


def upgrade() -> None:
    flow_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'chat_session',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('client_id', sa.String(length=128), nullable=False),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name='chat_session_pkey'),
        sa.UniqueConstraint('client_id', name='chat_session_client_id_key'),
    )
    op.create_index('chat_session_client_id_idx', 'chat_session', ['client_id'], unique=False)

    op.create_table(
        'chat_conversation',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('flow_type', flow_type, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('preview', sa.String(length=255), nullable=True),
        sa.Column('active_replay_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chat_session.id'], name='chat_conversation_session_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='chat_conversation_pkey'),
    )
    op.create_index('chat_conversation_session_id_idx', 'chat_conversation', ['session_id'], unique=False)

    op.create_table(
        'chat_thread',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('flow_type', flow_type, nullable=False),
        sa.Column('workflow_id', sa.String(length=255), nullable=True),
        sa.Column('dbos_workflow_id', sa.String(length=255), nullable=True),
        sa.Column('task_queue', sa.String(length=255), nullable=True),
        sa.Column('replay_id', sa.String(length=255), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['chat_conversation.id'], name='chat_thread_conversation_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='chat_thread_pkey'),
        sa.UniqueConstraint('conversation_id', name='chat_thread_conversation_id_key'),
    )
    op.create_index('chat_thread_conversation_id_idx', 'chat_thread', ['conversation_id'], unique=False)

    op.create_table(
        'chat_message',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('ui_message_json', sa.JSON(), nullable=False),
        sa.Column('model_messages_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['chat_conversation.id'], name='chat_message_conversation_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='chat_message_pkey'),
        sa.UniqueConstraint('conversation_id', 'sequence', name='chat_message_conversation_id_sequence_key'),
    )
    op.create_index('chat_message_conversation_id_idx', 'chat_message', ['conversation_id'], unique=False)


def downgrade() -> None:
    op.drop_index('chat_message_conversation_id_idx', table_name='chat_message')
    op.drop_table('chat_message')
    op.drop_index('chat_thread_conversation_id_idx', table_name='chat_thread')
    op.drop_table('chat_thread')
    op.drop_index('chat_conversation_session_id_idx', table_name='chat_conversation')
    op.drop_table('chat_conversation')
    op.drop_index('chat_session_client_id_idx', table_name='chat_session')
    op.drop_table('chat_session')
    flow_type.drop(op.get_bind(), checkfirst=True)
