"""drop unique constraint on session mcp_session_id

Revision ID: 24842fa39da7
Revises: bb07edf29ef1
Create Date: 2026-02-26 12:49:15.109956

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '24842fa39da7'
down_revision = 'bb07edf29ef1'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('session_mcp_session_id_key', 'session', type_='unique')


def downgrade():
    op.create_unique_constraint('session_mcp_session_id_key', 'session', ['mcp_session_id'], postgresql_nulls_not_distinct=False)
