"""add schedule types and logs

Revision ID: b1c2d3e4f5a6
Revises: ac4b4b9ca090
Create Date: 2026-04-08 10:00:00.000000

Changes:
- Add schedule_type column (VARCHAR, NOT NULL, default 'static_prompt') to agent_schedule
- Add command column (TEXT, nullable) to agent_schedule
- Create agent_schedule_log table with all execution log fields
- Create indexes on schedule_id, agent_id, executed_at
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'ac4b4b9ca090'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add schedule_type and command columns to agent_schedule
    op.add_column(
        'agent_schedule',
        sa.Column(
            'schedule_type',
            sa.String(),
            nullable=False,
            server_default='static_prompt',
        )
    )
    op.add_column(
        'agent_schedule',
        sa.Column('command', sa.Text(), nullable=True)
    )

    # Create agent_schedule_log table
    op.create_table(
        'agent_schedule_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('schedule_id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('schedule_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('prompt_used', sa.Text(), nullable=True),
        sa.Column('command_executed', sa.Text(), nullable=True),
        sa.Column('command_output', sa.Text(), nullable=True),
        sa.Column('command_exit_code', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.Uuid(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['schedule_id'],
            ['agent_schedule.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['agent_id'],
            ['agent.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['session_id'],
            ['session.id'],
            ondelete='SET NULL',
        ),
    )

    # Create indexes
    op.create_index(
        'ix_agent_schedule_log_schedule_id',
        'agent_schedule_log',
        ['schedule_id'],
    )
    op.create_index(
        'ix_agent_schedule_log_agent_id',
        'agent_schedule_log',
        ['agent_id'],
    )
    op.create_index(
        'ix_agent_schedule_log_executed_at',
        'agent_schedule_log',
        ['executed_at'],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_agent_schedule_log_executed_at', table_name='agent_schedule_log')
    op.drop_index('ix_agent_schedule_log_agent_id', table_name='agent_schedule_log')
    op.drop_index('ix_agent_schedule_log_schedule_id', table_name='agent_schedule_log')

    # Drop table
    op.drop_table('agent_schedule_log')

    # Remove columns from agent_schedule
    op.drop_column('agent_schedule', 'command')
    op.drop_column('agent_schedule', 'schedule_type')
