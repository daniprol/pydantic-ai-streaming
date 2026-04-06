"""pending_tool_call_schema

Revision ID: d0b5e5f63e6b
Revises: 63f31954a072
Create Date: 2026-04-06 07:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd0b5e5f63e6b'
down_revision = '63f31954a072'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_pending_tool_call',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('tool_call_id', sa.String(length=255), nullable=False),
        sa.Column('pending_group_id', sa.String(length=255), nullable=False),
        sa.Column('tool_name', sa.String(length=255), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('approval', 'decision', 'form', name='pending_tool_call_kind'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('pending', 'resolved', 'denied', 'cancelled', name='pending_tool_call_status'),
            nullable=False,
        ),
        sa.Column('message_sequence', sa.Integer(), nullable=False),
        sa.Column('approval_id', sa.String(length=255), nullable=True),
        sa.Column(
            'args_json',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column(
            'request_metadata_json',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column(
            'ui_payload_json',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column(
            'resolution_json',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column(
            'resume_model_messages_json',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['chat_conversation.id'],
            name=op.f('chat_pending_tool_call_conversation_id_fkey'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('chat_pending_tool_call_pkey')),
        sa.UniqueConstraint('tool_call_id', name=op.f('chat_pending_tool_call_tool_call_id_key')),
    )
    op.create_index(
        op.f('chat_pending_tool_call_conversation_id_idx'),
        'chat_pending_tool_call',
        ['conversation_id'],
        unique=False,
    )
    op.create_index(
        op.f('chat_pending_tool_call_pending_group_id_idx'),
        'chat_pending_tool_call',
        ['pending_group_id'],
        unique=False,
    )
    op.create_index(
        op.f('chat_pending_tool_call_status_idx'),
        'chat_pending_tool_call',
        ['status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('chat_pending_tool_call_status_idx'), table_name='chat_pending_tool_call')
    op.drop_index(
        op.f('chat_pending_tool_call_pending_group_id_idx'), table_name='chat_pending_tool_call'
    )
    op.drop_index(
        op.f('chat_pending_tool_call_conversation_id_idx'), table_name='chat_pending_tool_call'
    )
    op.drop_table('chat_pending_tool_call')
    sa.Enum(name='pending_tool_call_status').drop(op.get_bind(), checkfirst=False)
    sa.Enum(name='pending_tool_call_kind').drop(op.get_bind(), checkfirst=False)
