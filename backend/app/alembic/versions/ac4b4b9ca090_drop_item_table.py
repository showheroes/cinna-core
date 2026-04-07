"""drop item table

Revision ID: ac4b4b9ca090
Revises: 559320c34180
Create Date: 2026-04-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ac4b4b9ca090'
down_revision = '559320c34180'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("item")


def downgrade():
    op.create_table(
        "item",
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
