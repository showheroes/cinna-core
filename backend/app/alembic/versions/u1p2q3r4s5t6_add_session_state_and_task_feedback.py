"""add session state and task feedback fields

Revision ID: u1p2q3r4s5t6
Revises: t0o1p2q3r4s5
Create Date: 2026-01-23

Adds result_state/result_summary to session table for agent-declared outcomes.
Adds auto_feedback/feedback_delivered to input_task for bi-directional agent communication.
Adds auto_feedback to agent_handover_config.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'u1p2q3r4s5t6'
down_revision = 't0o1p2q3r4s5'
branch_labels = None
depends_on = None


def upgrade():
    # Session: agent-declared outcome fields
    op.add_column('session', sa.Column('result_state', sa.String(), nullable=True))
    op.add_column('session', sa.Column('result_summary', sa.Text(), nullable=True))

    # InputTask: auto-feedback control
    op.add_column('input_task', sa.Column('auto_feedback', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('input_task', sa.Column('feedback_delivered', sa.Boolean(), nullable=False, server_default='false'))

    # AgentHandoverConfig: auto-feedback default for new tasks
    op.add_column('agent_handover_config', sa.Column('auto_feedback', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    op.drop_column('agent_handover_config', 'auto_feedback')
    op.drop_column('input_task', 'feedback_delivered')
    op.drop_column('input_task', 'auto_feedback')
    op.drop_column('session', 'result_summary')
    op.drop_column('session', 'result_state')
