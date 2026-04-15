"""add prompt_examples to app_agent_route and identity_agent_binding

Revision ID: b5a73df91425
Revises: ff3bdb6d86a6, f7d39032b418
Create Date: 2026-04-15

"""
from alembic import op
import sqlalchemy as sa

revision = 'b5a73df91425'
down_revision = ('ff3bdb6d86a6', 'f7d39032b418')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('app_agent_route', sa.Column('prompt_examples', sa.Text(), nullable=True))
    op.add_column('identity_agent_binding', sa.Column('prompt_examples', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('identity_agent_binding', 'prompt_examples')
    op.drop_column('app_agent_route', 'prompt_examples')
