"""add_model_override_fields_to_environment

Revision ID: f0920ee2eeab
Revises: h3i4j5k6l7m8
Create Date: 2026-03-21 14:28:52.579459

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'f0920ee2eeab'
down_revision = 'h3i4j5k6l7m8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_environment', sa.Column('model_override_conversation', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('agent_environment', sa.Column('model_override_building', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade():
    op.drop_column('agent_environment', 'model_override_building')
    op.drop_column('agent_environment', 'model_override_conversation')
