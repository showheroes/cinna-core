"""remove ready task status - convert to refining

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-01-18

Removes 'ready' status from task lifecycle.
Existing 'ready' tasks are converted to 'refining'.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'm3h4i5j6k7l8'
down_revision = 'l2g3h4i5j6k7'
branch_labels = None
depends_on = None


def upgrade():
    # Convert existing 'ready' tasks to 'refining'
    op.execute(
        "UPDATE input_task SET status = 'refining' WHERE status = 'ready'"
    )


def downgrade():
    # No downgrade needed - 'refining' is a valid status
    # Tasks that were 'ready' will stay as 'refining'
    pass
