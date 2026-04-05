"""add_absurd_flow_type

Revision ID: 6f5df1e587f1
Revises: 63f31954a072
Create Date: 2026-04-05 17:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '6f5df1e587f1'
down_revision = '63f31954a072'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE flow_type ADD VALUE IF NOT EXISTS 'absurd'")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    op.execute("DELETE FROM chat_conversation WHERE flow_type = 'absurd'")
    op.execute('ALTER TYPE flow_type RENAME TO flow_type_old')
    op.execute("CREATE TYPE flow_type AS ENUM ('basic', 'dbos', 'temporal', 'dbos-replay')")
    op.execute(
        sa.text(
            'ALTER TABLE chat_conversation ALTER COLUMN flow_type TYPE flow_type USING flow_type::text::flow_type'
        )
    )
    op.execute('DROP TYPE flow_type_old')
