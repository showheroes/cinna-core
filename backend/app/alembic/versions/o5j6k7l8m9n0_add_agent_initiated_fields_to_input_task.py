"""add agent_initiated fields to input_task

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
Create Date: 2026-01-18

Adds agent_initiated, auto_execute, and source_session_id fields to input_task table
for supporting agent-to-agent handover through task creation.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'o5j6k7l8m9n0'
down_revision = 'n4i5j6k7l8m9'
branch_labels = None
depends_on = None


def upgrade():
    # Add agent_initiated flag - marks tasks created by agents
    op.add_column('input_task', sa.Column('agent_initiated', sa.Boolean(), nullable=False, server_default='false'))

    # Add auto_execute flag - triggers auto-execution after creation
    op.add_column('input_task', sa.Column('auto_execute', sa.Boolean(), nullable=False, server_default='false'))

    # Add source_session_id - links to the session that initiated the handover
    op.add_column('input_task', sa.Column('source_session_id', sa.UUID(), nullable=True))

    # Add foreign key constraint for source_session_id
    op.create_foreign_key(
        'fk_input_task_source_session_id',
        'input_task',
        'session',
        ['source_session_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    # Drop foreign key first
    op.drop_constraint('fk_input_task_source_session_id', 'input_task', type_='foreignkey')

    # Drop columns
    op.drop_column('input_task', 'source_session_id')
    op.drop_column('input_task', 'auto_execute')
    op.drop_column('input_task', 'agent_initiated')
