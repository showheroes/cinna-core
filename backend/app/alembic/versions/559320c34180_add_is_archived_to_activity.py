"""add is_archived to activity

Revision ID: 559320c34180
Revises: 86d07eb9fbf5
Create Date: 2026-04-06 09:09:36.868090

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '559320c34180'
down_revision = '86d07eb9fbf5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('activity', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade():
    op.drop_column('activity', 'is_archived')
