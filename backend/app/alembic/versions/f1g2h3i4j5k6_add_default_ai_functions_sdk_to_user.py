"""add default_ai_functions_sdk to user

Revision ID: f1g2h3i4j5k6
Revises: e1f2g3h4i5j6
Create Date: 2026-03-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1g2h3i4j5k6'
down_revision = 'e1f2g3h4i5j6'
branch_labels = None
depends_on = None


def upgrade():
    # Add default_ai_functions_sdk preference field to user table.
    # Controls which provider is used for AI utility functions (title generation,
    # agent config generation, prompt refinement, SQL generation, etc.).
    # "system" = use system-configured providers (default, backward compatible)
    # "anthropic" = use the user's personal Anthropic AICredential
    op.add_column(
        'user',
        sa.Column(
            'default_ai_functions_sdk',
            sa.String(length=50),
            nullable=True,
            server_default='system',
        ),
    )
    # Ensure existing rows have the default value explicitly set
    op.execute("UPDATE \"user\" SET default_ai_functions_sdk = 'system' WHERE default_ai_functions_sdk IS NULL")


def downgrade():
    op.drop_column('user', 'default_ai_functions_sdk')
