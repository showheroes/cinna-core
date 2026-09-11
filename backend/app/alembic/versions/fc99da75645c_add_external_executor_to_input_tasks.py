"""add external executor to input tasks

Revision ID: fc99da75645c
Revises: 8f3a1d7c04e2
Create Date: 2026-09-11 19:20:40.650659

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# revision identifiers, used by Alembic.
revision = 'fc99da75645c'
down_revision = '8f3a1d7c04e2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "input_task",
        sa.Column("external_executor", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    )


def downgrade():
    op.drop_column("input_task", "external_executor")
