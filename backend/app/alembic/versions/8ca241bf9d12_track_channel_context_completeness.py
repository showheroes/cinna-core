"""Track whether an ingested channel message was fully included.

Revision ID: 8ca241bf9d12
Revises: 2450acc74033
"""

import sqlalchemy as sa
from alembic import op

revision = "8ca241bf9d12"
down_revision = "2450acc74033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "channel_thread_ingest_log",
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Historical entries predate completeness tracking. Let an explicit quote
    # retrieve them again; live-message deduplication remains intact.
    op.execute("UPDATE channel_thread_ingest_log SET is_complete = false WHERE source != 'live'")
    op.alter_column("channel_thread_ingest_log", "is_complete", server_default=None)


def downgrade():
    op.drop_column("channel_thread_ingest_log", "is_complete")
