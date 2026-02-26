"""make mcp_oauth_client connector_id nullable

Revision ID: bb07edf29ef1
Revises: dc259404533e
Create Date: 2026-02-26 09:28:40.936530

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bb07edf29ef1'
down_revision = 'dc259404533e'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('mcp_oauth_client', 'connector_id',
               existing_type=sa.UUID(),
               nullable=True)


def downgrade():
    op.alter_column('mcp_oauth_client', 'connector_id',
               existing_type=sa.UUID(),
               nullable=False)
