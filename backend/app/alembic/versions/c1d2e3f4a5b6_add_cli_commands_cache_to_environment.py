"""add cli commands cache to environment

Revision ID: c1d2e3f4a5b6
Revises: 34322f866173
Create Date: 2026-04-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = '34322f866173'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_environment', sa.Column('cli_commands_raw', sa.Text(), nullable=True))
    op.add_column('agent_environment', sa.Column('cli_commands_parsed', sa.JSON(), nullable=True))
    op.add_column('agent_environment', sa.Column('cli_commands_fetched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agent_environment', sa.Column('cli_commands_error', sa.String(length=256), nullable=True))


def downgrade():
    op.drop_column('agent_environment', 'cli_commands_error')
    op.drop_column('agent_environment', 'cli_commands_fetched_at')
    op.drop_column('agent_environment', 'cli_commands_parsed')
    op.drop_column('agent_environment', 'cli_commands_raw')
