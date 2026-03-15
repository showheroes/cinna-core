"""add agent collaboration tables

Revision ID: f55c23690563
Revises: b3029a8e84ac
Create Date: 2026-03-15 08:11:24.493953

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'f55c23690563'
down_revision = 'b3029a8e84ac'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_collaboration',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('coordinator_agent_id', sa.Uuid(), nullable=False),
        sa.Column('source_session_id', sa.Uuid(), nullable=True),
        sa.Column('shared_context', sa.JSON(), nullable=True),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['coordinator_agent_id'], ['agent.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_session_id'], ['session.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'collaboration_subtask',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('collaboration_id', sa.Uuid(), nullable=False),
        sa.Column('target_agent_id', sa.Uuid(), nullable=False),
        sa.Column('task_message', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('result_summary', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('input_task_id', sa.Uuid(), nullable=True),
        sa.Column('session_id', sa.Uuid(), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['collaboration_id'], ['agent_collaboration.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['input_task_id'], ['input_task.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['session.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['target_agent_id'], ['agent.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('collaboration_subtask')
    op.drop_table('agent_collaboration')
