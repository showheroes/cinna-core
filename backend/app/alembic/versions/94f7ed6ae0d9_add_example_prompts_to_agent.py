"""add example_prompts to agent

Revision ID: 94f7ed6ae0d9
Revises: 24842fa39da7
Create Date: 2026-02-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '94f7ed6ae0d9'
down_revision = '24842fa39da7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent', sa.Column('example_prompts', sa.JSON(), server_default='[]', nullable=True))


def downgrade():
    op.drop_column('agent', 'example_prompts')
