"""add a2a_config field

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-01-15

Adds a2a_config JSON field to agent table for storing A2A protocol configuration:
- skills: List of agent skills for A2A discovery
- version: Semantic version for the agent card
- generated_at: Timestamp of when skills were last generated
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent', sa.Column('a2a_config', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('agent', 'a2a_config')
