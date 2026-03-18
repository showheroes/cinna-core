"""rename ai_functions_sdk values to personal: prefix

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-03-18 14:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'h3i4j5k6l7m8'
down_revision = 'g2h3i4j5k6l7'
branch_labels = None
depends_on = None


def upgrade():
    # Rename "anthropic" to "personal:anthropic" to distinguish personal credentials
    # from future system-level Anthropic provider.
    op.execute(
        "UPDATE \"user\" SET default_ai_functions_sdk = 'personal:anthropic' "
        "WHERE default_ai_functions_sdk = 'anthropic'"
    )


def downgrade():
    op.execute(
        "UPDATE \"user\" SET default_ai_functions_sdk = 'anthropic' "
        "WHERE default_ai_functions_sdk = 'personal:anthropic'"
    )
