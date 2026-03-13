"""add fk user_dashboard_block agent_id

Revision ID: a7b8c9d0e1f2
Revises: 0045add3641e
Create Date: 2026-03-13 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = '0045add3641e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_foreign_key(
        'fk_user_dashboard_block_agent_id',
        'user_dashboard_block',
        'agent',
        ['agent_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade():
    op.drop_constraint('fk_user_dashboard_block_agent_id', 'user_dashboard_block', type_='foreignkey')
