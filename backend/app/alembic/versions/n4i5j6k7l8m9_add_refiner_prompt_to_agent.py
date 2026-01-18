"""add refiner_prompt to agent

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2026-01-18

Adds refiner_prompt field to Agent model for task refinement instructions.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'n4i5j6k7l8m9'
down_revision = 'm3h4i5j6k7l8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent', sa.Column('refiner_prompt', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('agent', 'refiner_prompt')
