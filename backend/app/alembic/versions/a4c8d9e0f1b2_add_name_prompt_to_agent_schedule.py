"""add name and prompt to agent_schedule, drop timezone

Revision ID: a4c8d9e0f1b2
Revises: 3b7ae224b1c7
Create Date: 2026-03-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'a4c8d9e0f1b2'
down_revision = '3b7ae224b1c7'
branch_labels = None
depends_on = None


def upgrade():
    # Add name column with server_default for existing rows
    op.add_column('agent_schedule', sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), server_default='', nullable=False))
    # Add prompt column (nullable TEXT)
    op.add_column('agent_schedule', sa.Column('prompt', sa.Text(), nullable=True))

    # Backfill: set name from description (first 80 chars) for existing rows
    op.execute("UPDATE agent_schedule SET name = LEFT(description, 80) WHERE name = ''")

    # Remove the server_default now that existing rows are backfilled
    op.alter_column('agent_schedule', 'name', server_default=None)

    # Drop timezone column
    op.drop_column('agent_schedule', 'timezone')


def downgrade():
    # Re-add timezone column
    op.add_column('agent_schedule', sa.Column('timezone', sa.VARCHAR(), server_default='UTC', nullable=False))
    # Remove server_default
    op.alter_column('agent_schedule', 'timezone', server_default=None)
    # Drop new columns
    op.drop_column('agent_schedule', 'prompt')
    op.drop_column('agent_schedule', 'name')
