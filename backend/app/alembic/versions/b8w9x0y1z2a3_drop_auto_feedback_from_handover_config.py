"""Drop auto_feedback from agent_handover_config

Revision ID: b8w9x0y1z2a3
Revises: ff3bdb6d86a6
Create Date: 2026-04-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8w9x0y1z2a3"
down_revision = "ff3bdb6d86a6"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('agent_handover_config', 'auto_feedback')


def downgrade():
    op.add_column('agent_handover_config', sa.Column('auto_feedback', sa.Boolean(), nullable=False, server_default='true'))
